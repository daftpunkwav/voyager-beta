"""notes 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。

聚合运行时装配根传入共享 SettingsStore(设置项注册进同一 store,§8.8,
设置页聚合渲染;独立运行省略时设置项不注册,服务功能不受影响)。
start/stop 是回收站保留策略的清理循环:启动清一次,之后每 24 小时一轮;
retention_days=0 时为 no-op(§9.20 惰性维护,无独立 worker 进程)。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from . import assets
from .capabilities import Deps, init_deps, registry
from .settings import DEFS
from .store import NoteStore


class TrashPruner:
    """回收站保留策略后台任务;Wiring.start/stop 的载体。"""

    def __init__(self, store: NoteStore, settings_store: SettingsStore | None,
                 purge_assets: Callable[[str], list[str]] | None = None) -> None:
        self._store = store
        self._settings = settings_store
        self._purge_assets = purge_assets
        self._task: asyncio.Task | None = None

    def _retention_days(self) -> int:
        if self._settings is None:
            return 30  # 独立运行未装配设置时按默认策略
        try:
            return int(self._settings.get("notes.trash.retention_days") or 0)
        except (TypeError, ValueError):
            return 30

    async def _loop(self) -> None:
        await asyncio.sleep(5.0)  # 避让进程启动高峰
        while True:
            purged = self._store.purge_expired(self._retention_days())
            for nid in purged:
                # wiring 层直接持有 asset purge;循环引用规避:capabilities 注册后再绑定
                if self._purge_assets:
                    self._purge_assets(nid)
            await asyncio.sleep(24 * 3600)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
    workspace: str | Path | None = None,
) -> Wiring:
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    history_keep = int((settings_store.get("notes.history.per_note") if settings_store else 20) or 0)
    store = NoteStore(Path(data_dir) / "notes.db", history_keep=history_keep)
    workspace = Path(workspace) if workspace else Path(__file__).parents[2] / "workspace"
    asset_store = assets.AssetStore(Path(data_dir) / "assets.db")

    def _max_asset_mb() -> int:
        if settings_store is None:
            return 20
        try:
            return int(settings_store.get("notes.assets.max_mb") or 20)
        except (TypeError, ValueError):
            return 20

    assets.init_store(asset_store, workspace, max_file_mb=_max_asset_mb)
    assets.register(registry)
    purge_assets = assets.purge_of_note
    init_deps(Deps(store=store, bus=bus, settings=settings_store,
                   purge_assets=purge_assets, workspace=workspace))
    pruner = TrashPruner(store, settings_store, purge_assets=purge_assets)

    def close() -> None:
        store.close()
        asset_store.close()

    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        start=pruner.start,
        stop=pruner.stop,
        close=close,
        # 附件只读路由:wire 已 init_store,自建自交,装配根零领域知识
        extra_router=assets.build_assets_router(),
    )
