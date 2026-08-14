"""sources 聚合 REST 入口(§13.1):进入本目录即可独立起进程。

运行:uvicorn rest:app_factory --factory --port 8010
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus
from platform_secrets import SecretStore

from .capabilities import SourcesDeps, init_all, registry
from .modules.books.store import BookStore
from .modules.news.store import NewsStore
from .modules.repo.store import RepoStore
from .modules.repo.worker import RepoWorker

_DEFAULT_DATA = Path(__file__).parent / "data"
_DEFAULT_WORKSPACE = Path(__file__).parents[2] / "workspace"


def create_app(
    data_dir: str | Path = _DEFAULT_DATA,
    workspace: str | Path = _DEFAULT_WORKSPACE,
    bus: EventBus | None = None,
) -> FastAPI:
    data_dir = Path(data_dir)
    repo_store = RepoStore(data_dir / "repo.db")
    book_store = BookStore(data_dir / "books.db")
    news_store = NewsStore(data_dir / "news.db")
    queue: asyncio.Queue = asyncio.Queue()
    init_all(SourcesDeps(
        repo_store=repo_store, book_store=book_store, news_store=news_store,
        secrets=SecretStore(data_dir / "secrets.db"), bus=bus,
        repo_queue=queue, workspace=Path(workspace),
    ))
    worker = RepoWorker(repo_store, bus, queue, Path(workspace))

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await worker.start()
        yield
        await worker.stop()
        repo_store.close()
        book_store.close()
        news_store.close()

    app = FastAPI(title="sources", lifespan=lifespan)
    app.include_router(build_router(registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="sources", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
