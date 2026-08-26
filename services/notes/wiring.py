"""notes 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。

聚合运行时装配根传入共享 SettingsStore(设置项注册进同一 store,§8.8,
设置页聚合渲染;独立运行省略时设置项不注册,服务功能不受影响)。
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import Deps, init_deps, registry
from .settings import DEFS
from .store import NoteStore


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    store = NoteStore(Path(data_dir) / "notes.db")
    init_deps(Deps(store=store, bus=bus, settings=settings_store))
    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        close=store.close,
    )
