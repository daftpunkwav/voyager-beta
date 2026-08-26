"""doc(Word 类)子模块注册表(§8.6)。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus

from ...store import DocumentStore

_DOMAIN = "office"
_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="office.doc")
registry = Registry("office.doc")


@dataclass
class DocDeps:
    store: DocumentStore
    bus: EventBus | None


_deps: DocDeps | None = None


def init_deps(deps: DocDeps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> DocDeps:
    if _deps is None:
        raise RuntimeError("deps 未注入")
    return _deps


def _require_doc(did: str) -> dict[str, Any]:
    doc = _require_deps().store.get(did)
    if doc is None or doc["kind"] != "doc":
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"文档不存在: {did}")
    return doc


async def _emit(type_: str, did: str, **payload) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type=type_, actor=_ACTOR, payload={"doc_id": did, **payload})
        )


@capability(registry, name="create_doc", description="创建 Word 类文档")
async def create_doc(title: str, blocks: list[dict] | None = None) -> dict[str, Any]:
    deps = _require_deps()
    doc = deps.store.create(title, "doc", blocks)
    await _emit("doc.created", doc["id"], title=title)
    return doc


@capability(registry, name="get_doc", description="读取文档全部块")
def get_doc(doc_id: str) -> dict[str, Any]:
    return _require_doc(doc_id)


@capability(registry, name="update_doc", description="整体替换文档块")
async def update_doc(doc_id: str, blocks: list[dict]) -> dict[str, Any]:
    deps = _require_deps()
    _require_doc(doc_id)
    doc = deps.store.update(doc_id, blocks=blocks)
    await _emit("doc.edited", doc_id)
    return doc


@capability(registry, name="insert_block", description="在指定位置插入块")
async def insert_block(doc_id: str, index: int, block: dict) -> dict[str, Any]:
    deps = _require_deps()
    doc = _require_doc(doc_id)
    blocks: list[dict] = doc["blocks"]
    blocks.insert(max(0, min(index, len(blocks))), block)
    doc = deps.store.update(doc_id, blocks=blocks)
    await _emit("doc.edited", doc_id)
    return doc


@capability(registry, name="delete_doc", description="删除文档", reversible=False)
async def delete_doc(doc_id: str) -> dict[str, Any]:
    deps = _require_deps()
    doc = _require_doc(doc_id)
    deps.store.delete(doc_id)
    return {"deleted": doc_id, "title": doc["title"]}


__all__ = ["DocDeps", "init_deps", "registry"]
