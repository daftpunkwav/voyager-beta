"""注册表 → FastAPI app(服务独立入口,§13.1)。

运行:uvicorn rest:app_factory --factory --port 8070(在本目录内)。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_secrets import SecretStore

from .capabilities import Deps, init_deps, registry
from .store import ProviderStore

_DEFAULT_DATA = Path(__file__).parent / "data"


def create_app(data_dir: str | Path = _DEFAULT_DATA) -> FastAPI:
    data_dir = Path(data_dir)
    store = ProviderStore(data_dir / "llm.db")
    secrets = SecretStore(data_dir / "secrets.db")
    init_deps(Deps(store=store, secrets=secrets))

    app = FastAPI(title="llm")
    app.state.store = store
    app.include_router(build_router(registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="llm", status=HealthStatus.UP).to_dict()

    @app.on_event("shutdown")
    def _close() -> None:
        store.close()
        secrets.close()

    return app


def app_factory() -> FastAPI:
    return create_app()
