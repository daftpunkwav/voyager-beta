"""doc 子模块能力(§8.2):文档导入 / 列表 / 大纲 / 分章读取 / 检索 / 元数据 / 删除。

导入是长任务(§7.3):登记 → 入队解析 → 完成发 source.ready;
未知扩展名按"已存档"(stored)语义收下——资料库包罗万象,解析能力渐进。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import (
    ActorKind,
    ActorRef,
    ErrorSuffix,
    Event,
    JobRef,
    ServiceError,
)
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .._shared.text import valid_tag
from .store import DocStore

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

#: 可解析格式(extract.py 分发);其余格式走存档语义
PARSEABLE_EXTS = (".pdf", ".epub", ".docx", ".txt", ".md", ".markdown")

_DOC_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.doc")

_DEFAULT_MAX_FILE_MB = 200

# 与 books 同源的文件名清洗:防 title/文件名写逃逸 doc 目录
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *(f"COM{i}" for i in range(1, 10)),
                   *(f"LPT{i}" for i in range(1, 10))}


def _safe_filename(name: str) -> str:
    cleaned = _UNSAFE_FILENAME_RE.sub("_", name).strip(" .")[:120]
    if not cleaned:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "文件名清洗后为空:不能仅由路径分隔符/保留字符构成")
    if Path(cleaned).stem.upper() in _RESERVED_NAMES:
        cleaned = f"doc_{cleaned}"
    return cleaned


@dataclass
class DocDeps:
    store: DocStore
    bus: EventBus | None
    queue: asyncio.Queue  # 解析任务:doc_id
    workspace: Path  # 落盘根(workspace/doc/)
    settings: SettingsStore | None = None  # sources.doc.max_file_mb 读取

    def max_file_mb(self) -> int:
        raw = self.settings.get("sources.doc.max_file_mb") if self.settings else None
        return int(raw or _DEFAULT_MAX_FILE_MB)


_deps: DocDeps | None = None


def init_deps(deps: DocDeps) -> None:
    global _deps
    _deps = deps


def require_deps() -> DocDeps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _require_doc(did: str) -> dict:
    doc = require_deps().store.get(did)
    if doc is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"文档不存在: {did}")
    return doc


def _validate_input(file_path: str, title: str, tags: list[str],
                    max_file_mb: int) -> tuple[Path, str, str]:
    """返回 (源路径, 扩展名, 标题);校验失败抛 INVALID_INPUT。"""
    src = Path(file_path)
    if not src.is_file():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"文件不存在: {file_path}")
    if max_file_mb > 0 and src.stat().st_size > max_file_mb * 1024 * 1024:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"文件超过大小上限 {max_file_mb}MB",
                           hint="可用设置 sources.doc.max_file_mb 调整")
    for tag in tags:
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                               f"标签不合法: {tag}(≤32 字,禁 \\\"\\',[] 字符)")
    ext = src.suffix.lower()
    clean_title = title.strip() or src.stem.strip() or "未命名文档"
    return src, ext, clean_title[:200]


@capability(registry, name="add_document",
            description="导入文档入资料库并后台解析(PDF/EPUB/DOCX/TXT/MD 分章提取;"
                        "其他格式仅存档)。file_path 须为服务器可达路径"
                        "(浏览器上传经 /api/uploads 落 workspace/imports/ 后传入)。",
            long_running=True, cost=2)
async def add_document(file_path: str, title: str = "", tags: list[str] | None = None,
                       category: str = "", _actor: ActorRef = None) -> JobRef:
    deps = require_deps()
    # 先 jail 再 stat:避免用「文件不存在」泄露 jail 外路径
    if not _within(Path(file_path), deps.workspace):
        raise ServiceError(_DOMAIN, ErrorSuffix.FORBIDDEN,
                           "文件须位于 workspace/ 内(经 /api/uploads 上传)",
                           hint="agent 可先把文件下载/复制到 workspace/ 再导入")
    src, ext, clean_title = _validate_input(
        file_path, title, list(tags or []), deps.max_file_mb())
    dest_dir = Path(deps.workspace) / "doc"
    dest_dir.mkdir(parents=True, exist_ok=True)
    uid = uuid.uuid4().hex[:8]
    dest = dest_dir / f"{_safe_filename(clean_title)}_{uid}{ext}"
    await asyncio.to_thread(shutil.copy2, src, dest)
    status = "parsing" if ext in PARSEABLE_EXTS else "stored"
    did = deps.store.add({"title": clean_title, "filename": src.name, "ext": ext,
                          "local_path": str(dest), "category": category,
                          "tags": list(tags or []), "status": status})
    if deps.bus is not None:
        await deps.bus.publish(Event(
            type="source.added", actor=_DOC_ACTOR,
            payload={"source_id": did, "kind": "doc", "title": clean_title}))
    if status == "parsing":
        deps.queue.put_nowait(did)
    return JobRef(job_id=did)


@capability(registry, name="list_documents",
            description="文档列表(摘要,不含分章正文;§9.20)")
def list_documents(status: str = "", tag: str = "", query: str = "",
                   sort: str = "added", desc: bool = True,
                   limit: int = 200) -> list[dict]:
    return require_deps().store.list(status=status, tag=tag, query=query,
                                     sort=sort, desc=desc, limit=min(limit, 500))


@capability(registry, name="get_document",
            description="单个文档详情(含分章大纲,不含正文)")
def get_document(doc_id: str) -> dict:
    doc = _require_doc(doc_id)
    doc["sections"] = require_deps().store.sections_outline(doc_id)
    doc["total_sections"] = len(doc["sections"])
    return doc


@capability(registry, name="get_doc_section",
            description="按需取文档某一章全文(1 基章号;§9.20 全文层)")
def get_doc_section(doc_id: str, section_no: int = 1) -> dict:
    deps = require_deps()
    _require_doc(doc_id)
    section = deps.store.section(doc_id, section_no)
    if section is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND,
                           f"章不存在: {section_no}",
                           hint="get_document 先看大纲")
    section["doc_id"] = doc_id
    section["total_sections"] = deps.store.sections_count(doc_id)
    return section


@capability(registry, name="search_documents",
            description="文档全文检索:命中返回章号与片段")
def search_documents(query: str, limit: int = 20) -> list[dict]:
    if not query.strip():
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "query 不能为空")
    return require_deps().store.search_sections(query.strip(), min(limit, 50))


@capability(registry, name="set_document_meta",
            description="设置文档分类/标签/进度/备注/标题(与 set_repo_meta 对齐)")
def set_document_meta(doc_id: str, title: str | None = None,
                      category: str | None = None, tags: list[str] | None = None,
                      progress: str | None = None, note: str | None = None) -> dict:
    deps = require_deps()
    _require_doc(doc_id)
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                               f"标签不合法: {tag}")
    deps.store.set_meta(doc_id, title=title, category=category, tags=tags,
                        progress=progress, note=note)
    return deps.store.get(doc_id)


@capability(registry, name="remove_document",
            description="删除文档记录/分章与本地副本", reversible=False, cost=2)
async def remove_document(doc_id: str) -> dict:
    deps = require_deps()
    doc = _require_doc(doc_id)
    deps.store.remove(doc_id)
    if doc["local_path"] and _within(Path(doc["local_path"]), deps.workspace):
        # 本地文件清理由 worker 异步做(与解析同一队列,保序)
        deps.queue.put_nowait(("remove", doc_id, doc["local_path"]))
    if deps.bus is not None:
        await deps.bus.publish(Event(
            type="source.removed", actor=_DOC_ACTOR,
            payload={"source_id": doc_id, "kind": "doc", "title": doc["title"]}))
    return {"removed": doc_id, "title": doc["title"]}


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False
