"""settings 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。

聚合运行时装配根传入共享 SettingsStore(agent 与其他服务的设置项注册进同一
store,设置页才能聚合展示);共享实例由传入方持有,wiring 不负责关闭。
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import DEFS, Deps, init_deps, registry


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    store: SettingsStore | None = None,
) -> Wiring:
    owns = store is None
    store = store or SettingsStore(Path(data_dir) / "settings.db", bus)
    store.register_fresh(DEFS)  # 幂等:共享 store 场景下只补尚未注册的键
    init_deps(Deps(store=store))
    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        close=store.close if owns else None,
    )
