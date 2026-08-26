"""code-exec 装配:独立运行(rest.py)与聚合运行(deploy/)共用。"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import DEFS, Deps, init_deps, registry
from .store import ExecutionStore

_DEFAULT_RUNTIMES = [
    {"id": "python", "name": "Python 3", "image": "python:3.11-slim",
     "file_ext": ".py", "cmd": ["python"]},
    {"id": "node", "name": "Node.js 20", "image": "node:20-slim",
     "file_ext": ".js", "cmd": ["node"]},
    {"id": "shell", "name": "Shell (bash)", "image": "bash:5.2",
     "file_ext": ".sh", "cmd": ["bash"]},
]


def wire(
    data_dir: str | Path,
    *,
    workspace: str | Path,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    data_dir = Path(data_dir)
    workspace = Path(workspace)
    owns_settings = settings_store is None
    settings_store = settings_store or SettingsStore(data_dir / "settings.db", bus)
    settings_store.register_fresh(DEFS)
    store = ExecutionStore(data_dir / "code-exec.db")
    init_deps(Deps(store=store, settings=settings_store, bus=bus, workspace=workspace))

    def close() -> None:
        store.close()
        if owns_settings:
            settings_store.close()

    return Wiring(registry=registry, probe=lambda: {"status": "up"}, close=close)
