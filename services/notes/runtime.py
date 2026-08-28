"""notes 运行时:注册表、依赖注入、存在性校验、领域事件。不含具体能力。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .store import NoteStore

DOMAIN = "notes"
ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="notes.service")
registry = Registry(DOMAIN)

SORT_COL = {"updated": "updated_ts", "created": "created_ts", "title": "title"}
STATES = ("active", "archived", "trash", "all")


@dataclass
class Deps:
    store: NoteStore
    bus: EventBus | None
    settings: SettingsStore | None = None
    purge_assets: Callable[[str], list[str]] | None = None  # purge 时连带清附件
    workspace: Path | None = None  # import/export 的 jail 根;wire() 必填


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def require_alive(nid: str) -> dict:
    """取未在回收站的笔记(归档态可读可改)。"""
    note = require_deps().store.get(nid)
    if note is None or note["trashed_ts"] is not None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"笔记不存在: {nid}")
    return note


def get_any(nid: str) -> dict:
    """含回收站笔记均可按 id 直读(get/版本/恢复场景)。"""
    note = require_deps().store.get(nid)
    if note is None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"笔记不存在: {nid}")
    return note


async def emit(type_: str, note_id: str, **payload) -> None:
    deps = require_deps()
    if deps.bus is not None:
        await deps.bus.publish(
            Event(type=type_, actor=ACTOR,
                  payload={"note_id": note_id, **payload})
        )
