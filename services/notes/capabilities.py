"""notes 能力注册表(§8.3):CRUD + link_note;delete 不可逆(reversible=False)。

事件:note.created / note.edited / note.deleted(修订:旧版无删除事件,
活动页撤销需要)。
"""

from __future__ import annotations

from dataclasses import dataclass

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus

from .store import NoteStore

_DOMAIN = "notes"
_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="notes.service")
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    store: NoteStore
    bus: EventBus | None


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _require_note(nid: str) -> dict:
    note = _require_deps().store.get(nid)
    if note is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"笔记不存在: {nid}")
    return note


async def _emit(type_: str, note_id: str, **payload) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type=type_, actor=_ACTOR, payload={"note_id": note_id, **payload})
        )


@capability(registry, name="create_note", description="新建 Markdown 笔记", cost=2)
async def create_note(title: str, content: str = "", tags: list[str] | None = None,
                      source_id: str = "", node_id: str = "") -> dict:
    deps = _require_deps()
    nid = deps.store.create({"title": title, "content": content,
                             "tags": tags or [], "source_id": source_id,
                             "node_id": node_id})
    await _emit("note.created", nid, title=title)
    return deps.store.get(nid)


@capability(registry, name="update_note", description="更新笔记标题/正文/标签", cost=2)
async def update_note(note_id: str, title: str | None = None,
                      content: str | None = None,
                      tags: list[str] | None = None) -> dict:
    deps = _require_deps()
    _require_note(note_id)
    deps.store.update(note_id, title=title, content=content, tags=tags)
    await _emit("note.edited", note_id)
    return deps.store.get(note_id)


@capability(registry, name="delete_note", description="删除笔记(不可逆)", reversible=False)
async def delete_note(note_id: str) -> dict:
    deps = _require_deps()
    note = _require_note(note_id)
    deps.store.delete(note_id)
    await _emit("note.deleted", note_id, title=note["title"])
    return {"deleted": note_id, "title": note["title"]}


@capability(registry, name="list_notes", description="笔记摘要列表(标题/标签/摘要,不含全文)")
def list_notes(source_id: str | None = None, tag: str = "", limit: int = 100) -> list[dict]:
    return _require_deps().store.list(source_id=source_id, tag=tag, limit=limit)


@capability(registry, name="get_note", description="按需取笔记全文")
def get_note(note_id: str) -> dict:
    return _require_note(note_id)


@capability(registry, name="link_note", description="关联笔记到资源或图谱节点", cost=2)
async def link_note(note_id: str, source_id: str | None = None,
                    node_id: str | None = None) -> dict:
    deps = _require_deps()
    _require_note(note_id)
    deps.store.update(note_id, source_id=source_id, node_id=node_id)
    await _emit("note.edited", note_id, linked=True)
    return deps.store.get(note_id)
