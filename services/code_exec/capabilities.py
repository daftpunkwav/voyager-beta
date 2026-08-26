"""code-exec 能力注册表(§8.5):run_file / run_snippet / list_runtimes。

执行一次性,无持久环境;进度/结果经 task.* 事件,产物落 workspace/sandbox/artifacts。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, JobRef, ServiceError
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .executor import run_in_runtime
from .settings import DEFS
from .store import ExecutionStore

_DOMAIN = "code-exec"
_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="code-exec.service")
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    """服务运行时依赖,由 wiring 注入。"""

    store: ExecutionStore
    settings: SettingsStore
    bus: EventBus | None
    workspace: Path


_deps: Deps | None = None

#: fire-and-forget 任务必须持强引用:否则 GC 可能在完成前回收 Task,结果静默丢失
_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _runtimes() -> list[dict[str, Any]]:
    return _require_deps().settings.get("code_exec.runtimes") or []


def _find_runtime(runtime_id: str) -> dict[str, Any]:
    for r in _runtimes():
        if r.get("id") == runtime_id:
            return r
    raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"未知运行时: {runtime_id}")


def _settings() -> dict[str, Any]:
    s = _require_deps().settings
    return {
        "timeout": s.get("code_exec.timeout_seconds"),
        "memory_mb": s.get("code_exec.memory_mb"),
        "network": s.get("code_exec.network"),
        "use_host": s.get("code_exec.use_host"),
    }


async def _emit_progress(exec_id: str, progress: float) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type="task.progress", actor=_ACTOR,
                  payload={"job_id": exec_id, "progress": progress})
        )


async def _emit_completed(exec_id: str, result: dict[str, Any]) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type="task.completed", actor=_ACTOR,
                  payload={"job_id": exec_id, "result": result})
        )


async def _emit_failed(exec_id: str, error: str) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type="task.failed", actor=_ACTOR,
                  payload={"job_id": exec_id, "error": error})
        )


async def _run_code(exec_id: str, runtime_id: str, code: str) -> dict[str, Any]:
    deps = _require_deps()
    cfg = _settings()
    runtime = _find_runtime(runtime_id)
    deps.store.create(exec_id, runtime_id, kind="snippet")
    await _emit_progress(exec_id, 0.0)
    try:
        result = await run_in_runtime(
            runtime, code,
            timeout=cfg["timeout"],
            memory_mb=cfg["memory_mb"],
            network=cfg["network"],
            use_host_fallback=cfg["use_host"],
            workspace=deps.workspace,
        )
    except Exception as exc:  # noqa: BLE001  # 后台任务:配置/校验错误也必须落库并告知,不静默崩溃
        error = f"{type(exc).__name__}: {exc}"
        deps.store.finish(exec_id, "failed", -1, "", error[:500], "")
        await _emit_failed(exec_id, error[:300])
        return {"exec_id": exec_id, "runtime": runtime_id, "status": "failed",
                "exit_code": -1, "stdout": "", "stderr": error[:500],
                "artifact_dir": ""}
    deps.store.finish(
        exec_id, result.status, result.exit_code,
        result.stdout, result.stderr, result.artifact_dir,
    )
    summary = {
        "exec_id": exec_id,
        "runtime": runtime_id,
        "status": result.status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "artifact_dir": result.artifact_dir,
    }
    await _emit_progress(exec_id, 1.0)
    if result.status == "completed":
        await _emit_completed(exec_id, summary)
    else:
        await _emit_failed(exec_id, result.stderr or result.status)
    return summary


@capability(registry, name="list_runtimes",
            description="列出可用代码运行时(Python/Node/Shell 及可扩展运行时)")
def list_runtimes() -> list[dict[str, Any]]:
    return _runtimes()


@capability(registry, name="run_snippet",
            description="执行代码片段;立即返回 exec_id,结果经 task.completed/failed 事件")
async def run_snippet(runtime: str, code: str, _actor: ActorRef = None) -> JobRef:
    exec_id = uuid.uuid4().hex[:12]
    # 立即触发异步执行,调用方不阻塞(§7.3);任务持引用防 GC 静默回收
    _spawn(_run_code(exec_id, runtime, code))
    return JobRef(job_id=exec_id)


@capability(registry, name="run_file",
            description="读取 workspace/sandbox/ 下的代码文件并执行;返回 exec_id")
async def run_file(runtime: str, file_path: str, _actor: ActorRef = None) -> JobRef:
    deps = _require_deps()
    sandbox = (deps.workspace / "sandbox").resolve()
    target = (deps.workspace / "sandbox" / file_path).resolve()
    try:
        target.relative_to(sandbox)
    except ValueError as exc:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT,
            "file_path 必须位于 workspace/sandbox/ 下",
        ) from exc
    if not target.is_file():
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"文件不存在: {file_path}")
    code = target.read_text(encoding="utf-8")
    exec_id = uuid.uuid4().hex[:12]
    _spawn(_run_code(exec_id, runtime, code))
    return JobRef(job_id=exec_id)


__all__ = ["DEFS", "Deps", "init_deps", "registry"]
