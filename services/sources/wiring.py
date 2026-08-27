"""sources 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。

聚合服务内部子模块(repo/doc/web)各自脱耦:独立 store、独立队列;
本文件只做组合。聚合运行时装配根可传入共享 SecretStore 与共享
SettingsStore(设置项注册进同一 store,§8.8)。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_secrets import SecretStore
from platform_settings import SettingsStore

from .capabilities import SourcesDeps, init_all, registry
from .modules.doc.store import DocStore
from .modules.doc.worker import DocWorker
from .modules.repo.store import RepoStore
from .modules.repo.worker import RepoWorker
from .modules.web.store import WebStore
from .settings import DEFS


def wire(
    data_dir: str | Path,
    *,
    workspace: str | Path,
    bus: EventBus | None = None,
    secrets: SecretStore | None = None,
    clone_fn=None,
    parse_fn=None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    from .migration import migrate_legacy_books_news

    data_dir = Path(data_dir)
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    migrate_legacy_books_news(data_dir)
    repo_store = RepoStore(data_dir / "repo.db")
    doc_store = DocStore(data_dir / "doc.db")
    web_store = WebStore(data_dir / "web.db")
    owns_secrets = secrets is None
    secrets = secrets or SecretStore(data_dir / "secrets.db")
    repo_queue: asyncio.Queue = asyncio.Queue()
    doc_queue: asyncio.Queue = asyncio.Queue()
    init_all(SourcesDeps(
        repo_store=repo_store, doc_store=doc_store, web_store=web_store,
        secrets=secrets, bus=bus, repo_queue=repo_queue, doc_queue=doc_queue,
        workspace=Path(workspace), settings=settings_store,
    ))
    repo_worker = RepoWorker(repo_store, bus, repo_queue, Path(workspace),
                             clone_fn=clone_fn)
    doc_worker = DocWorker(doc_store, bus, doc_queue, Path(workspace),
                           parse_fn=parse_fn)

    async def start() -> None:
        await asyncio.gather(repo_worker.start(), doc_worker.start())

    async def stop() -> None:
        await asyncio.gather(repo_worker.stop(), doc_worker.stop())

    def close() -> None:
        repo_store.close()
        doc_store.close()
        web_store.close()
        if owns_secrets:
            secrets.close()

    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        start=start,
        stop=stop,
        close=close,
    )
