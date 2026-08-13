"""索引流水线：浅克隆 → 引擎 index_repository → 状态机（可并行）。"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import stat
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

from py_shared import error_codes as EC
from py_shared.exceptions import AppException, NotFoundError
from py_shared.models.graph_index import GraphIndexStatus
from py_shared.models.project import Project
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from graph_engine_runtime.client import GraphEngineClient, GraphEngineError
from graph_engine_runtime.context import get_runtime_context

logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()
# (project_id, owner, repo, mode, refresh, job_gen)
_INDEX_QUEUE: asyncio.Queue[tuple[UUID, str, str, str, bool, int]] | None = None
_INDEX_WORKERS: list[asyncio.Task[Any]] = []
_PROJECT_LOCKS: dict[UUID, asyncio.Lock] = {}
_PROJECT_LOCKS_GUARD = asyncio.Lock()
# 用户取消：阶段边界检查；与 job_gen 叠加，防止迟到写回
_CANCEL_REQUESTED: set[UUID] = set()
# 每次 trigger/cancel/delete/timeout 递增；过期 job 不得写 READY
_JOB_GEN: dict[UUID, int] = {}
# 已入队尚未被 worker 取走
_QUEUED_IDS: set[UUID] = set()
# worker 正在执行
_INFLIGHT: set[UUID] = set()

_OWNER_REPO_RE = re.compile(
    r"github\.com[/:](?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?/?$",
    re.I,
)
_TOKEN_IN_URL_RE = re.compile(r"(https?://)([^:@/]+):([^@/]+)@", re.I)
_ACTIVE_STATUSES = frozenset({"QUEUED", "CLONING", "INDEXING"})


def _bump_job_gen(project_id: UUID) -> int:
    n = _JOB_GEN.get(project_id, 0) + 1
    _JOB_GEN[project_id] = n
    return n


def _job_gen(project_id: UUID) -> int:
    return _JOB_GEN.get(project_id, 0)


def _job_alive(project_id: UUID, expected_gen: int) -> bool:
    """本代任务是否仍有效（取消/删除/超时会 bump gen）。"""
    return _job_gen(project_id) == expected_gen


def _safe_remove_dir(path: Path) -> None:
    """删除缓存目录。Windows 上文件锁导致删除失败时，改名到同级 .trash/。"""
    if not path.exists():
        return

    def _onerror(func: Any, p: str, _exc_info: Any) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    for attempt in range(3):
        try:
            shutil.rmtree(path, onerror=_onerror)
        except Exception:
            pass
        if not path.exists():
            return
        time.sleep(0.12 * (attempt + 1))

    trash_root = path.parent / ".trash"
    trash_root.mkdir(parents=True, exist_ok=True)
    trash = trash_root / f"{path.name}-{uuid.uuid4().hex[:8]}"
    try:
        path.rename(trash)
    except OSError as exc:
        raise RuntimeError(
            f"无法清理缓存目录 {path}（可能被占用）：{exc}。请关闭占用该目录的程序后重试。"
        ) from exc


def _cache_root() -> Path:
    root = _allowed_root() / "repo-cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _session_factory() -> Any:
    """DB 会话工厂（宿主 api_backend 注入）；短会话写状态专用，避免长锁。"""
    factory = get_runtime_context().get_session_factory
    if factory is None:
        raise RuntimeError("graph_engine_runtime 未注入 DB session factory")
    return factory()


def _is_under_dir(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _resolve_cache_dest(
    owner: str, repo: str, local_path: str | None, cache_root: Path
) -> Path:
    """仅允许复用 repo-cache 下的路径；否则回退到规范缓存目录。"""
    canonical = cache_dir_for(owner, repo, "head")
    if not local_path:
        return canonical
    candidate = Path(local_path)
    if _is_under_dir(candidate, cache_root) and candidate.exists():
        return candidate
    return canonical


async def _project_lock(project_id: UUID) -> asyncio.Lock:
    async with _PROJECT_LOCKS_GUARD:
        lock = _PROJECT_LOCKS.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            _PROJECT_LOCKS[project_id] = lock
        return lock


def _stale_age_sec() -> float:
    settings = get_runtime_context().settings
    return max(
        3600.0,
        float(settings.git_clone_timeout_sec)
        + float(settings.graph_index_timeout_sec)
        + 300.0,
    )


async def start_index_worker() -> None:
    """在 lifespan 启动常驻 worker 池（不受请求 cancel scope 影响）。"""
    global _INDEX_QUEUE, _INDEX_WORKERS
    alive = [w for w in _INDEX_WORKERS if not w.done()]
    if alive and _INDEX_QUEUE is not None:
        _INDEX_WORKERS = alive
        return

    settings = get_runtime_context().settings
    n = int(settings.index_concurrency)
    _INDEX_QUEUE = asyncio.Queue()
    _INDEX_WORKERS = []

    async def _worker(worker_id: int) -> None:
        assert _INDEX_QUEUE is not None
        while True:
            project_id, owner, repo, mode, refresh, job_gen = await _INDEX_QUEUE.get()
            _QUEUED_IDS.discard(project_id)
            t0 = time.perf_counter()
            _INFLIGHT.add(project_id)
            try:
                await _run_pipeline(
                    project_id,
                    owner,
                    repo,
                    mode=mode,
                    refresh=refresh,
                    job_gen=job_gen,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("索引 worker 未捕获异常 project=%s", project_id)
            finally:
                _INFLIGHT.discard(project_id)
                logger.debug(
                    "index worker=%s project=%s elapsed_ms=%s",
                    worker_id,
                    project_id,
                    int((time.perf_counter() - t0) * 1000),
                )
                _INDEX_QUEUE.task_done()

    for i in range(n):
        _INDEX_WORKERS.append(
            asyncio.create_task(_worker(i), name=f"graph-index-worker-{i}")
        )
    logger.info("索引 worker 池已启动 concurrency=%s", n)


async def stop_index_worker() -> None:
    global _INDEX_QUEUE, _INDEX_WORKERS
    for w in _INDEX_WORKERS:
        if not w.done():
            w.cancel()
    for w in _INDEX_WORKERS:
        try:
            await w
        except (asyncio.CancelledError, Exception):
            pass
    _INDEX_WORKERS = []
    _INDEX_QUEUE = None
    _QUEUED_IDS.clear()
    _INFLIGHT.clear()


def classify_index_error(error: str | None) -> str:
    """将错误文案归类为 network / service / cancelled / unknown，供 UI 展示。"""
    if not error:
        return "unknown"
    low = error.lower()
    if "取消" in error or "cancel" in low:
        return "cancelled"
    if any(
        k in low
        for k in (
            "timeout",
            "timed out",
            "connection",
            "network",
            "dns",
            "unreachable",
            "ssl",
            "proxy",
            "getaddrinfo",
            "failed to connect",
            "could not resolve",
            "连接",
            "网络",
            "超时",
        )
    ):
        return "network"
    if any(
        k in low
        for k in (
            "engine",
            "graph_fallback",
            "502",
            "503",
            "500",
            "internal",
            "sqlite",
            "disk",
            "quota",
            "permission",
            "already exists",
            "not an empty directory",
            "服务",
            "引擎",
            "命令失败",
        )
    ):
        return "service"
    return "unknown"


def _format_pipeline_error(exc: BaseException) -> str:
    """生成可读错误；避免空 str(exc) 与 URL 中的 token 泄露。"""
    if isinstance(exc, AppException) and isinstance(exc.detail, dict):
        msg = str(exc.detail.get("message") or exc.detail)
    elif isinstance(exc, asyncio.CancelledError):
        msg = "索引任务被取消（常见于 API --reload 重启），请重新点击索引"
    else:
        msg = str(exc).strip() or repr(exc)
    msg = _TOKEN_IN_URL_RE.sub(r"\1***:***@", msg)
    return f"{type(exc).__name__}: {msg}"[:2000]


def _spawn_pipeline(
    project_id: UUID,
    owner: str,
    repo: str,
    *,
    mode: str,
    refresh: bool,
    job_gen: int,
) -> None:
    """投递到 lifespan worker 队列；worker 未就绪时退化为带强引用的 create_task。"""
    if _INDEX_QUEUE is not None:
        _QUEUED_IDS.add(project_id)
        _INDEX_QUEUE.put_nowait((project_id, owner, repo, mode, refresh, job_gen))
        return

    async def _runner() -> None:
        _INFLIGHT.add(project_id)
        try:
            await _run_pipeline(
                project_id, owner, repo, mode=mode, refresh=refresh, job_gen=job_gen
            )
        finally:
            _INFLIGHT.discard(project_id)

    task = asyncio.create_task(_runner(), name=f"graph-index-{project_id}")
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def parse_github_owner_repo(url: str) -> tuple[str, str]:
    raw = (url or "").strip()
    m = _OWNER_REPO_RE.search(raw)
    if m:
        return m.group("owner"), m.group("repo")
    parsed = urlparse(raw)
    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) >= 2:
        return parts[0], parts[1].removesuffix(".git")
    raise ValueError(f"无法从 URL 解析 owner/repo: {url}")


def engine_project_name(owner: str, repo: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{owner}-{repo}").strip("-")
    return f"graph-{safe}"[:200]


def _allowed_root() -> Path:
    settings = get_runtime_context().settings
    return Path(settings.graph_allowed_root)


def cache_dir_for(owner: str, repo: str, sha7: str = "head") -> Path:
    """构造 repo-cache 下的缓存目录（owner/repo 先 sanitize，防路径穿越）。

    与 engine_project_name 同一套字符白名单：仅保留 [A-Za-z0-9._-]，
    其余替换为 '-'，杜绝 Windows 下 '\\..' 跳出 cache_root（CWE-22）。
    """
    root = _cache_root()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{owner}-{repo}-{sha7}").strip("-")
    name = safe[:180] or "repo"
    dest = root / name
    if not _is_under_dir(dest, root):
        raise ValueError(f"非法缓存目录: {name!r}")
    return dest


async def get_or_create_status(
    db: AsyncSession, project_id: UUID
) -> GraphIndexStatus:
    result = await db.execute(
        select(GraphIndexStatus).where(GraphIndexStatus.project_id == project_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    row = GraphIndexStatus(project_id=project_id, status="NONE", index_mode="fast")
    db.add(row)
    await db.flush()
    return row


def _row_is_stale(row: GraphIndexStatus, *, max_age_sec: float) -> bool:
    """仅 CLONING/INDEXING 且不在 inflight 时可判僵尸（QUEUED 可能只是排队）。"""
    if row.status not in ("CLONING", "INDEXING"):
        return False
    if row.project_id in _INFLIGHT:
        return False
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_sec)
    ts = row.updated_at or row.created_at
    return bool(ts and ts < cutoff)


async def _fail_stale_row(db: AsyncSession, row: GraphIndexStatus, max_age_sec: float) -> bool:
    if not _row_is_stale(row, max_age_sec=max_age_sec):
        return False
    _bump_job_gen(row.project_id)
    row.status = "INDEX_FAILED"
    row.error = f"索引超时未完成（>{int(max_age_sec)}s），请用 fast 模式重试"
    row.updated_at = datetime.utcnow()
    await db.commit()
    return True


async def get_status_out(db: AsyncSession, project_id: UUID) -> dict:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError("项目不存在", EC.PROJECT_NOT_FOUND)
    row = await get_or_create_status(db, project_id)
    await _fail_stale_row(db, row, _stale_age_sec())
    await db.refresh(row)
    return _status_dict(row)


def _status_dict(row: GraphIndexStatus) -> dict:
    err = row.error
    return {
        "project_id": str(row.project_id),
        "engine_project": row.engine_project or "",
        "local_path": row.local_path,
        "head_sha": row.head_sha,
        "branch": row.branch,
        "status": row.status,
        "index_mode": row.index_mode,
        "node_count": row.node_count,
        "edge_count": row.edge_count,
        "indexed_at": row.indexed_at.isoformat() if row.indexed_at else None,
        "error": err,
        "error_kind": classify_index_error(err),
        "cancel_requested": row.project_id in _CANCEL_REQUESTED,
    }


async def list_index_statuses(db: AsyncSession) -> list[dict]:
    """全部项目索引状态（图谱页进度条）。顺带清理超长僵尸任务。"""
    try:
        await recover_stale_jobs(db, max_age_sec=_stale_age_sec())
    except Exception:
        logger.warning("清理僵尸索引状态失败", exc_info=True)
    result = await db.execute(select(GraphIndexStatus))
    rows = result.scalars().all()
    return [_status_dict(r) for r in rows]


def _raise_if_cancelled(project_id: UUID, job_gen: int) -> None:
    if not _job_alive(project_id, job_gen) or project_id in _CANCEL_REQUESTED:
        raise asyncio.CancelledError("用户取消索引")


async def cancel_index(db: AsyncSession, project_id: UUID) -> dict:
    """取消排队中或进行中的索引；已完成则 no-op。"""
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError("项目不存在", EC.PROJECT_NOT_FOUND)
    row = await get_or_create_status(db, project_id)
    if row.status not in _ACTIVE_STATUSES:
        return _status_dict(row)

    # 作废队列中的旧 job_gen，防止出队后继续跑 / 迟到 READY
    _bump_job_gen(project_id)
    _CANCEL_REQUESTED.add(project_id)
    row.status = "INDEX_FAILED"
    row.error = "用户取消索引"
    row.updated_at = datetime.utcnow()
    await db.commit()
    if project_id not in _INFLIGHT and project_id not in _QUEUED_IDS:
        _CANCEL_REQUESTED.discard(project_id)
    return _status_dict(row)


async def recover_interrupted_jobs(db: AsyncSession) -> int:
    """启动时将中断的 CLONING/INDEXING/QUEUED 标为失败，供用户重试。"""
    result = await db.execute(
        update(GraphIndexStatus)
        .where(GraphIndexStatus.status.in_(("QUEUED", "CLONING", "INDEXING")))
        .values(
            status="INDEX_FAILED",
            error="进程重启，索引任务中断，请重试",
            updated_at=datetime.utcnow(),
        )
    )
    await db.commit()
    return (result.rowcount or 0)  # type: ignore[attr-defined]


async def recover_stale_jobs(
    db: AsyncSession, *, max_age_sec: float = 3600.0
) -> int:
    """清理长时间无进度的 CLONING/INDEXING（不含 QUEUED，避免误杀排队任务）。"""
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_sec)
    # 仍在执行的不算僵尸
    inflight = list(_INFLIGHT)
    stmt = (
        update(GraphIndexStatus)
        .where(
            GraphIndexStatus.status.in_(("CLONING", "INDEXING")),
            (
                (GraphIndexStatus.updated_at.is_not(None)
                 & (GraphIndexStatus.updated_at < cutoff))
                | (
                    GraphIndexStatus.updated_at.is_(None)
                    & (GraphIndexStatus.created_at < cutoff)
                )
            ),
        )
        .values(
            status="INDEX_FAILED",
            error=f"索引超时未完成（>{int(max_age_sec)}s），请用 fast 模式重试",
            updated_at=datetime.utcnow(),
        )
    )
    if inflight:
        stmt = stmt.where(GraphIndexStatus.project_id.notin_(inflight))
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0)  # type: ignore[attr-defined]


def _is_job_tracked(project_id: UUID) -> bool:
    return project_id in _QUEUED_IDS or project_id in _INFLIGHT


async def trigger_index(
    db: AsyncSession,
    project_id: UUID,
    *,
    mode: str = "fast",
    refresh: bool = False,
) -> dict:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError("项目不存在", EC.PROJECT_NOT_FOUND)

    row = await get_or_create_status(db, project_id)
    await _fail_stale_row(db, row, _stale_age_sec())
    await db.refresh(row)

    # 真正在队列/执行中才短路；孤儿 QUEUED/CLONING/INDEXING 允许重入队
    if row.status in _ACTIVE_STATUSES and _is_job_tracked(project_id):
        return _status_dict(row)

    try:
        owner, repo = parse_github_owner_repo(project.url)
    except ValueError as exc:
        raise AppException(400, EC.PROJECT_URL_INVALID, str(exc)) from exc

    job_gen = _bump_job_gen(project_id)
    _CANCEL_REQUESTED.discard(project_id)
    row.status = "QUEUED"
    row.index_mode = mode
    row.error = None
    row.engine_project = engine_project_name(owner, repo)
    row.updated_at = datetime.utcnow()
    await db.commit()

    _spawn_pipeline(
        project_id, owner, repo, mode=mode, refresh=refresh, job_gen=job_gen
    )
    return _status_dict(row)


async def delete_index(db: AsyncSession, project_id: UUID) -> dict:
    """删除索引：作废进行中任务 + 清理本地 clone 缓存 + 删除引擎图谱 + 重置状态。"""
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError("项目不存在", EC.PROJECT_NOT_FOUND)
    row = await get_or_create_status(db, project_id)

    # 作废一切进行中的写回（含迟到 READY）
    _bump_job_gen(project_id)
    _CANCEL_REQUESTED.add(project_id)

    owner = repo = ""
    try:
        owner, repo = parse_github_owner_repo(project.url)
    except ValueError:
        pass

    cache_root = _cache_root()
    candidates: list[Path] = []
    if row.local_path:
        candidates.append(Path(row.local_path))
    if owner and repo:
        candidates.append(cache_dir_for(owner, repo, "head"))
    seen: set[str] = set()
    for path in candidates:
        if not _is_under_dir(path, cache_root):
            logger.warning("拒绝删除允许根外路径 path=%s", path)
            continue
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists() and path.is_dir():
            try:
                await asyncio.to_thread(_safe_remove_dir, path)
            except Exception:
                logger.warning("删除仓库缓存失败 path=%s", path, exc_info=True)

    engine_name = (row.engine_project or "").strip()
    if not engine_name and owner and repo:
        engine_name = engine_project_name(owner, repo)
    if engine_name:
        try:
            await GraphEngineClient().drop_project(engine_name)
        except Exception:
            logger.warning(
                "删除引擎图谱失败 engine=%s", engine_name, exc_info=True
            )

    row.status = "NONE"
    row.local_path = None
    row.head_sha = None
    row.branch = None
    row.engine_project = ""
    row.node_count = None
    row.edge_count = None
    row.indexed_at = None
    row.error = None
    row.index_mode = "fast"
    row.updated_at = datetime.utcnow()
    await db.commit()
    # 写回防护靠 job_gen + status==NONE；cancel 仅用于 UI/阶段边界
    if project_id not in _INFLIGHT:
        _CANCEL_REQUESTED.discard(project_id)
    return _status_dict(row)


async def _patch_status(
    project_id: UUID,
    *,
    expected_gen: int,
    status: str | None = None,
    error: str | None = None,
    clear_error: bool = False,
    local_path: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    engine_project: str | None = None,
    node_count: int | None = None,
    edge_count: int | None = None,
    indexed_at: datetime | None = None,
    index_mode: str | None = None,
) -> str:
    """短会话写状态；job_gen 过期或已删除(NONE)时拒绝进度/READY 写回。"""
    last: BaseException | None = None
    for i in range(8):
        try:
            factory = _session_factory()
            async with factory() as db:
                row = await get_or_create_status(db, project_id)
                prev = row.status
                if _job_gen(project_id) != expected_gen:
                    return prev
                # 删除后禁止任何进度写回
                if row.status == "NONE" and status in (
                    "CLONING",
                    "INDEXING",
                    "READY",
                    "QUEUED",
                ):
                    return prev
                if status is not None:
                    row.status = status
                if clear_error:
                    row.error = None
                elif error is not None:
                    row.error = error
                if local_path is not None:
                    row.local_path = local_path
                if head_sha is not None:
                    row.head_sha = head_sha
                if branch is not None:
                    row.branch = branch
                if engine_project is not None:
                    row.engine_project = engine_project
                if node_count is not None:
                    row.node_count = node_count
                if edge_count is not None:
                    row.edge_count = edge_count
                if indexed_at is not None:
                    row.indexed_at = indexed_at
                if index_mode is not None:
                    row.index_mode = index_mode
                row.updated_at = datetime.utcnow()
                await db.commit()
                return prev
        except Exception as exc:
            last = exc
            msg = str(exc).lower()
            if "locked" not in msg and "busy" not in msg:
                raise
            await asyncio.sleep(0.05 * (2**i))
    assert last is not None
    raise last


async def _run_pipeline(
    project_id: UUID,
    owner: str,
    repo: str,
    *,
    mode: str,
    refresh: bool,
    job_gen: int,
) -> None:
    # 队列中的过期/已取消任务直接丢弃
    if _job_gen(project_id) != job_gen:
        _CANCEL_REQUESTED.discard(project_id)
        return

    lock = await _project_lock(project_id)
    async with lock:
        phase = "QUEUED"
        try:
            if _job_gen(project_id) != job_gen:
                return
            factory = _session_factory()
            async with factory() as db:
                project = await db.get(Project, project_id)
                if not project:
                    return
                project_url = project.url
                row = await get_or_create_status(db, project_id)
                # 必须以 QUEUED 启动；取消/删除后不应再跑
                if row.status != "QUEUED" or _job_gen(project_id) != job_gen:
                    return
                if project_id in _CANCEL_REQUESTED:
                    row.status = "INDEX_FAILED"
                    row.error = "用户取消索引"
                    row.updated_at = datetime.utcnow()
                    await db.commit()
                    return
                local_path = row.local_path

            await _clone_and_index(
                project_id,
                owner,
                repo,
                mode=mode,
                refresh=refresh,
                project_url=project_url,
                local_path=local_path,
                job_gen=job_gen,
            )
        except BaseException as exc:
            try:
                factory = _session_factory()
                async with factory() as db:
                    row = await get_or_create_status(db, project_id)
                    phase = row.status
            except Exception:
                pass

            logger.exception(
                "索引流水线失败 project=%s status=%s err=%s",
                project_id,
                phase,
                _format_pipeline_error(exc),
            )
            try:
                if _job_gen(project_id) != job_gen:
                    return
                user_cancel = project_id in _CANCEL_REQUESTED or (
                    isinstance(exc, asyncio.CancelledError)
                    and "用户取消" in str(exc)
                )
                if user_cancel:
                    await _patch_status(
                        project_id,
                        expected_gen=job_gen,
                        status="INDEX_FAILED",
                        error="用户取消索引",
                    )
                else:
                    fail_status = (
                        "CLONE_FAILED"
                        if phase in ("CLONING", "QUEUED")
                        else "INDEX_FAILED"
                    )
                    await _patch_status(
                        project_id,
                        expected_gen=job_gen,
                        status=fail_status,
                        error=_format_pipeline_error(exc),
                    )
            except Exception:
                logger.exception("写入失败状态时二次异常 project=%s", project_id)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            # worker 收尾始终清本项目 cancel，避免删除/取消后残留
            _CANCEL_REQUESTED.discard(project_id)


def _is_usable_git_checkout(path: Path) -> bool:
    """可复用的工作区：有 .git，且至少有一个非 .git 条目（避免半截 clone 空壳）。"""
    if not path.is_dir() or not (path / ".git").exists():
        return False
    try:
        for child in path.iterdir():
            if child.name != ".git":
                return True
    except OSError:
        return False
    return False


async def _clone_and_index(
    project_id: UUID,
    owner: str,
    repo: str,
    *,
    mode: str,
    refresh: bool,
    project_url: str,
    local_path: str | None,
    job_gen: int,
) -> None:
    """clone + index：长耗时步骤在 DB 会话外执行，避免 SQLite 长时间锁。"""
    settings = get_runtime_context().settings
    cache_root = _cache_root()
    await asyncio.to_thread(_enforce_quota, cache_root, settings.repo_cache_quota_gb)

    await _patch_status(
        project_id,
        expected_gen=job_gen,
        status="CLONING",
        clear_error=True,
        index_mode=mode,
    )
    _raise_if_cancelled(project_id, job_gen)

    token: str | None = None
    try:
        ctx = get_runtime_context()
        if ctx.get_session_factory is None or ctx.app_state_service is None:
            raise RuntimeError("未注入 DB/AppState 服务")
        factory = ctx.get_session_factory()
        async with factory() as db:
            state = await ctx.app_state_service.get_or_create_app_state(db)
            if ctx.primary_token is not None:
                _, token = ctx.primary_token(state)
    except Exception:
        token = None

    dest = _resolve_cache_dest(owner, repo, local_path, cache_root)

    t_clone0 = time.perf_counter()
    reuse = False

    if _is_usable_git_checkout(dest) and _is_under_dir(dest, cache_root):
        reuse = True
        if refresh:
            await _git_pull(dest, token=token)
    else:
        if dest.exists() and _is_under_dir(dest, cache_root):
            await asyncio.to_thread(_safe_remove_dir, dest)
        dest = cache_dir_for(owner, repo, "head")
        timeout = float(settings.git_clone_timeout_sec)
        try:
            await asyncio.wait_for(
                _git_shallow_clone(project_url, dest, token=token),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            await _patch_status(
                project_id,
                expected_gen=job_gen,
                status="CLONE_FAILED",
                error=(
                    f"浅克隆超时（{timeout:.0f}s）：{owner}/{repo}。"
                    "请检查网络后重试，或改用 fast 模式。"
                ),
            )
            _bump_job_gen(project_id)
            raise RuntimeError(
                f"浅克隆超时（{timeout:.0f}s）：{owner}/{repo}。请检查网络后重试，或改用 fast 模式。"
            ) from exc

    clone_ms = int((time.perf_counter() - t_clone0) * 1000)
    sha = await _git_rev_parse(dest)
    branch = await _git_branch(dest)
    eng = engine_project_name(owner, repo)
    _raise_if_cancelled(project_id, job_gen)
    await _patch_status(
        project_id,
        expected_gen=job_gen,
        status="INDEXING",
        local_path=str(dest.resolve()),
        head_sha=sha,
        branch=branch,
        engine_project=eng,
        clear_error=True,
    )
    _raise_if_cancelled(project_id, job_gen)

    client = GraphEngineClient(timeout=float(settings.graph_index_timeout_sec))
    if not await client.health():
        raise GraphEngineError(
            "图谱引擎不可用。请构建并启动本仓 C 引擎（services/graph_engine/graph_engine_core，默认 http://127.0.0.1:9750），"
            "或检查 GRAPH_ENGINE_URL / GRAPH_ENGINE_BIN；亦可清空 URL 以回退 Python graph_fallback。",
            code=EC.GRAPH_ENGINE_UNAVAILABLE,
        )

    t_idx0 = time.perf_counter()
    idx_timeout = float(settings.graph_index_timeout_sec)

    def _should_abandon() -> bool:
        return not _job_alive(project_id, job_gen)

    try:
        result = await asyncio.wait_for(
            client.index_repository(
                str(dest.resolve()),
                mode=mode,
                name=eng,
                persistence=True,
                should_abandon=_should_abandon,
            ),
            timeout=idx_timeout,
        )
    except asyncio.TimeoutError as exc:
        # 先落库失败，再作废本代，阻止线程收尾写 READY；引擎 should_abandon 跳过 persist
        msg = (
            f"索引超时（{idx_timeout:.0f}s）：{owner}/{repo}。"
            "请改用 fast 模式或缩小仓库。"
        )
        await _patch_status(
            project_id,
            expected_gen=job_gen,
            status="INDEX_FAILED",
            error=msg,
        )
        _bump_job_gen(project_id)
        raise GraphEngineError(msg, code=EC.GRAPH_INDEX_FAILED) from exc
    except GraphEngineError:
        raise
    except Exception as exc:
        raise GraphEngineError(
            f"索引失败：{exc}", code=EC.GRAPH_INDEX_FAILED
        ) from exc

    if isinstance(result, dict) and result.get("abandoned"):
        raise asyncio.CancelledError("用户取消索引")

    index_ms = int((time.perf_counter() - t_idx0) * 1000)
    _raise_if_cancelled(project_id, job_gen)

    node_count: int | None = None
    edge_count: int | None = None
    if isinstance(result, dict):
        if result.get("nodes") is not None:
            try:
                node_count = int(result["nodes"])
            except (TypeError, ValueError):
                pass
        if result.get("edges") is not None:
            try:
                edge_count = int(result["edges"])
            except (TypeError, ValueError):
                pass
    if node_count is None or edge_count is None:
        try:
            schema = await client.get_graph_schema(eng)
            if isinstance(schema, dict):
                if node_count is None:
                    node_count = sum(
                        int(x.get("count") or 0)
                        for x in (schema.get("node_labels") or [])
                    )
                if edge_count is None:
                    edge_count = sum(
                        int(x.get("count") or 0)
                        for x in (schema.get("edge_types") or [])
                    )
        except Exception:
            logger.warning("无法读取 graph schema 统计", exc_info=True)

    await _patch_status(
        project_id,
        expected_gen=job_gen,
        status="READY",
        clear_error=True,
        node_count=node_count,
        edge_count=edge_count,
        indexed_at=datetime.utcnow(),
        local_path=str(dest.resolve()),
        head_sha=sha,
        branch=branch,
        engine_project=eng,
    )
    logger.info(
        "索引完成 %s/%s mode=%s reuse=%s clone_ms=%s index_ms=%s nodes=%s",
        owner,
        repo,
        mode,
        reuse,
        clone_ms,
        index_ms,
        node_count,
    )


def _dir_size_bytes(root: Path, *, max_files: int = 200_000) -> int:
    """估算目录体积；限制扫描文件数，避免每次索引扫爆整个 cache。"""
    total = 0
    n = 0
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".trash"]
            for name in filenames:
                try:
                    total += (Path(dirpath) / name).stat().st_size
                except OSError:
                    pass
                n += 1
                if n >= max_files:
                    return total
    except OSError:
        pass
    return total


def _enforce_quota(cache_root: Path, quota_gb: float) -> None:
    total = _dir_size_bytes(cache_root)
    if total > quota_gb * 1024**3:
        raise AppException(
            400,
            EC.GRAPH_INDEX_FAILED,
            f"仓库缓存已超过配额 {quota_gb}GB，请删除旧索引后重试",
        )


def _build_credential_args(token: str | None) -> tuple[list[str], dict | None]:
    """构造 git credential 注入参数（`-c` 前缀段 + 子进程 env）。

    - token 为 None：匿名访问，不注入任何 helper。
    - 有 token：先 `-c credential.helper=` 清空（-c 是累加而非替换，系统级
      credential.helper=manager 会先接管 credential fill 导致非交互挂起），
      再注入内联 helper；token 仅经 env 传给 helper 子进程，不进 cmdline。
    - token 含换行/空字符会截断 helper 的 echo 输出、覆盖 username 字段
      （credential 协议无转义机制），直接拒绝（SEC-004）。
    """
    if token is None:
        return [], None
    if any(ch in token for ch in ("\n", "\r", "\x00")):
        raise AppException(
            400,
            EC.GITHUB_PAT_INVALID,
            "GitHub PAT 含非法控制字符（换行/空字符）",
        )
    helper = (
        "!f() { echo username=x-access-token; "
        "echo \"password=$GRAPH_GIT_TOKEN\"; }; f"
    )
    env = os.environ.copy()
    env["GRAPH_GIT_TOKEN"] = token
    return (
        ["-c", "credential.helper=", "-c", f"credential.helper={helper}"],
        env,
    )


async def _git_shallow_clone(
    url: str, dest: Path, *, token: str | None = None
) -> None:
    # SSRF 防线：仅允许 https://github.com，并一律按 parsed.path 重构
    # clone_url，丢弃用户原始 URL 的 scheme/userinfo/port/query/fragment。
    # 此前匿名分支原样透传 url、仅靠 host 字符串校验兜底，与 token 分支
    # （已重构 URL）不对称且脆弱（SEC-007 加固）。
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != "github.com":
        raise AppException(
            400,
            EC.PROJECT_URL_INVALID,
            "仅支持 https://github.com 仓库",
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    path = parsed.path or ""
    clone_url = f"https://github.com{path}"
    if not clone_url.endswith(".git"):
        clone_url += ".git"

    credential_args, env = _build_credential_args(token)
    # 使用 -c 局部配置，避免污染用户全局 git config
    staging = dest.parent / f".clone-{uuid.uuid4().hex[:10]}"
    base = ["git", "-c", "core.longpaths=true", "-c", "core.symlinks=false"]
    base += credential_args
    attempts = [
        [
            *base,
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--single-branch",
            clone_url,
            str(staging),
        ],
        [
            *base,
            "clone",
            "--depth",
            "1",
            "--single-branch",
            clone_url,
            str(staging),
        ],
    ]
    last_err: Optional[BaseException] = None
    try:
        for attempt_i, cmd in enumerate(attempts):
            if staging.exists():
                await asyncio.to_thread(_safe_remove_dir, staging)
            try:
                await _run_cmd(cmd, env=env)
                if dest.exists():
                    await asyncio.to_thread(_safe_remove_dir, dest)
                staging.rename(dest)
                return
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "浅克隆失败 attempt=%s: %s",
                    attempt_i,
                    _format_pipeline_error(exc),
                )
                if staging.exists():
                    try:
                        await asyncio.to_thread(_safe_remove_dir, staging)
                    except Exception:
                        logger.warning("清理失败的 staging 目录失败: %s", staging)
    finally:
        if staging.exists():
            try:
                await asyncio.to_thread(_safe_remove_dir, staging)
            except Exception:
                logger.warning("最终清理 staging 失败: %s", staging)
    assert last_err is not None
    raise last_err


async def _git_pull(dest: Path, *, token: str | None = None) -> None:
    # refresh 路径同样注入凭据：fetch 对私有仓库需要 credential helper，
    # 否则系统级 manager helper 接管（凭据混淆/非交互挂起，与 clone 同类 bug）。
    credential_args, env = _build_credential_args(token)
    await _run_cmd(
        ["git", "-C", str(dest), *credential_args, "fetch", "--depth", "1"],
        env=env,
    )
    branch = await _git_branch(dest)
    await _run_cmd(
        ["git", "-C", str(dest), "reset", "--hard", f"origin/{branch}"],
        check=False,
    )


async def _git_rev_parse(dest: Path) -> str:
    out = await _run_cmd(["git", "-C", str(dest), "rev-parse", "HEAD"])
    return out.strip()[:40]


async def _git_branch(dest: Path) -> str:
    out = await _run_cmd(
        ["git", "-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"],
        check=False,
    )
    return (out or "HEAD").strip() or "HEAD"


def _run_cmd_sync(cmd: list[str], *, check: bool = True, env: dict | None = None) -> str:
    """线程内同步执行 git（部分 Windows 事件循环不支持 asyncio subprocess）。"""
    try:
        completed = subprocess.run(cmd, capture_output=True, check=False, env=env)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "未找到 git 可执行文件，请确认已安装 Git 且 API 进程 PATH 可用"
        ) from exc
    if check and completed.returncode != 0:
        err = (completed.stderr or completed.stdout or b"").decode(
            "utf-8", errors="replace"
        )[:1500]
        safe_cmd = [_TOKEN_IN_URL_RE.sub(r"\1***:***@", c) for c in cmd]
        # stderr 也可能回显带凭据的 URL，一并脱敏再进异常消息
        safe_err = _TOKEN_IN_URL_RE.sub(r"\1***:***@", err)
        raise RuntimeError(
            f"命令失败 ({completed.returncode}): {' '.join(safe_cmd)}\n{safe_err}"
        )
    return (completed.stdout or b"").decode("utf-8", errors="replace")


async def _run_cmd(cmd: list[str], *, check: bool = True, env: dict | None = None) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "未找到 git 可执行文件，请确认已安装 Git 且 API 进程 PATH 可用"
        ) from exc
    except NotImplementedError:
        return await asyncio.to_thread(_run_cmd_sync, cmd, check=check, env=env)

    try:
        stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:
        # wait_for 超时/取消时杀掉 git，避免孤儿进程与半截目录
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        raise

    if check and proc.returncode != 0:
        err = (stderr or stdout or b"").decode("utf-8", errors="replace")[:1500]
        safe_cmd = [_TOKEN_IN_URL_RE.sub(r"\1***:***@", c) for c in cmd]
        # stderr 也可能回显带凭据的 URL，一并脱敏再进异常消息
        safe_err = _TOKEN_IN_URL_RE.sub(r"\1***:***@", err)
        raise RuntimeError(f"命令失败 ({proc.returncode}): {' '.join(safe_cmd)}\n{safe_err}")
    return (stdout or b"").decode("utf-8", errors="replace")
