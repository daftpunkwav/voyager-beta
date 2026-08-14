"""注册表 → FastAPI app(服务独立入口:进入目录即可起进程,§13.1)。

运行:uvicorn rest:app_factory --factory --port 8090(在本目录内)
或经 gateway 聚合挂载。模块级无副作用(import 不建库不起 worker)。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from capabilities import Deps, init_deps, registry
from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus
from store import JobStore
from worker import Worker

_DEFAULT_DB = Path(__file__).parent / "data" / "template.db"


def create_app(
    db_path: str | Path = _DEFAULT_DB, bus: EventBus | None = None
) -> FastAPI:
    store = JobStore(db_path)
    queue: asyncio.Queue = asyncio.Queue()
    worker = Worker(store, bus, queue)
    init_deps(Deps(store=store, bus=bus, queue=queue))

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await worker.start()
        yield
        await worker.stop()
        store.close()

    app = FastAPI(title="template", lifespan=lifespan)
    app.state.store = store
    app.include_router(build_router(registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="template", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
