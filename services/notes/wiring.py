"""notes 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus

from .capabilities import Deps, init_deps, registry
from .store import NoteStore


def wire(data_dir: str | Path, *, bus: EventBus | None = None) -> Wiring:
    store = NoteStore(Path(data_dir) / "notes.db")
    init_deps(Deps(store=store, bus=bus))
    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        close=store.close,
    )
