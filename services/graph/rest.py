"""graph 服务 REST 入口(§13.1):uvicorn rest:app_factory --factory --port 8030"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from capabilities import Deps, init_deps, registry
from engines.adapter import EngineAdapter
from fastapi import FastAPI
from index_queue import IndexQueue
from pipelines.code.analyze import analyze_repo
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus
from scheduler import IndexScheduler
from store import GraphStore

_DEFAULT_DATA = Path(__file__).parent / "data"


def create_app(
    data_dir: str | Path = _DEFAULT_DATA,
    bus: EventBus | None = None,
    *,
    c_url: str = "http://127.0.0.1:8123",
    engine_mode: str = "auto",
    scheduler: IndexScheduler | None = None,
) -> FastAPI:
    data_dir = Path(data_dir)
    store = GraphStore(data_dir / "graph.db")
    queue = IndexQueue(data_dir / "index.db")
    adapter = EngineAdapter(c_base_url=c_url,
                            python_data_root=data_dir / "engine-python",
                            bus=bus, mode=engine_mode)
    init_deps(Deps(store=store, queue=queue, adapter=adapter, bus=bus))

    async def _run_job(job: dict) -> None:
        await analyze_repo(adapter, store, project=job["project"],
                           repo_path=job["repo_path"])

    sched = scheduler or IndexScheduler(queue, _run_job, bus)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await sched.start()
        yield
        await sched.stop()
        store.close()
        queue.close()

    app = FastAPI(title="graph", lifespan=lifespan)
    app.include_router(build_router(registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="graph", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
