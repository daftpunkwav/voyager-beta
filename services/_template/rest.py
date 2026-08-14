"""注册表 → FastAPI app(服务独立入口:仓库根起进程,§13.1)。

运行:uvicorn services._template.rest:app_factory --factory --port 8090
或经 gateway 聚合挂载。模块级无副作用(import 不建库不起 worker)。
装配逻辑全部在 wiring.py;本文件只是 HTTP 薄壳。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus

from .wiring import wire

_DEFAULT_DATA = Path(__file__).parent / "data"


def create_app(
    data_dir: str | Path = _DEFAULT_DATA, bus: EventBus | None = None
) -> FastAPI:
    w = wire(data_dir, bus=bus)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if w.start:
            await w.start()
        yield
        if w.stop:
            await w.stop()
        if w.close:
            w.close()

    app = FastAPI(title="template", lifespan=lifespan)
    app.include_router(build_router(w.registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="template", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
