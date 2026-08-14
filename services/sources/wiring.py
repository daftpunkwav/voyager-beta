"""sources 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。

聚合服务内部子模块(repo/books/news)各自脱耦:独立 store、独立 wiring 入口;
本文件只做组合。聚合运行时装配根可传入共享 SecretStore。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_secrets import SecretStore

from .capabilities import SourcesDeps, init_all, registry
from .modules.books.store import BookStore
from .modules.news.store import NewsStore
from .modules.repo.store import RepoStore
from .modules.repo.worker import RepoWorker


def wire(
    data_dir: str | Path,
    *,
    workspace: str | Path,
    bus: EventBus | None = None,
    secrets: SecretStore | None = None,
    clone_fn=None,
) -> Wiring:
    data_dir = Path(data_dir)
    repo_store = RepoStore(data_dir / "repo.db")
    book_store = BookStore(data_dir / "books.db")
    news_store = NewsStore(data_dir / "news.db")
    owns_secrets = secrets is None
    secrets = secrets or SecretStore(data_dir / "secrets.db")
    queue: asyncio.Queue = asyncio.Queue()
    init_all(SourcesDeps(
        repo_store=repo_store, book_store=book_store, news_store=news_store,
        secrets=secrets, bus=bus, repo_queue=queue, workspace=Path(workspace),
    ))
    worker = RepoWorker(repo_store, bus, queue, Path(workspace), clone_fn=clone_fn)

    def close() -> None:
        repo_store.close()
        book_store.close()
        news_store.close()
        if owns_secrets:
            secrets.close()

    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        start=worker.start,
        stop=worker.stop,
        close=close,
    )
