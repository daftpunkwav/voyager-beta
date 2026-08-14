"""settings 服务 REST 入口(§13.1):uvicorn rest:app_factory --factory --port 8080"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import DEFS, Deps, init_deps, registry

_DEFAULT_DB = Path(__file__).parent / "data" / "settings.db"


def create_app(db_path: str | Path = _DEFAULT_DB, bus: EventBus | None = None) -> FastAPI:
    store = SettingsStore(db_path, bus)
    store.register(DEFS)  # 本服务自有 defs;其余服务的 defs 由部署入口聚合注册
    init_deps(Deps(store=store))

    app = FastAPI(title="settings")
    app.include_router(build_router(registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="settings", status=HealthStatus.UP).to_dict()

    @app.on_event("shutdown")
    def _close() -> None:
        store.close()

    return app


def app_factory() -> FastAPI:
    return create_app()
