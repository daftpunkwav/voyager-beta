"""sources 聚合注册表(§6.4/§8.2):仅合并子模块注册表,零业务逻辑。

子模块在 modules/ 下自包含,互不 import;壳只读合并(依赖矩阵 §12)。
新增资源类型 = modules/ 下新增自包含目录 + 此处一行注册,其余零改动。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from modules.books import capabilities as books_caps
from modules.books.store import BookStore
from modules.news import capabilities as news_caps
from modules.news.store import NewsStore
from modules.repo import capabilities as repo_caps
from modules.repo.store import RepoStore
from platform_capability import Registry
from platform_eventbus import EventBus
from platform_secrets import SecretStore

registry = Registry("sources")
registry.merge(repo_caps.registry, books_caps.registry, news_caps.registry)


@dataclass
class SourcesDeps:
    """聚合层统一装配的子模块依赖。"""

    repo_store: RepoStore
    book_store: BookStore
    news_store: NewsStore
    secrets: SecretStore
    bus: EventBus | None
    repo_queue: asyncio.Queue
    workspace: Path


def init_all(deps: SourcesDeps) -> None:
    repo_caps.init_deps(repo_caps.RepoDeps(
        store=deps.repo_store, secrets=deps.secrets, bus=deps.bus,
        queue=deps.repo_queue, workspace=deps.workspace,
    ))
    books_caps.init_deps(books_caps.BookDeps(
        store=deps.book_store, workspace=deps.workspace,
    ))
    news_caps.init_deps(news_caps.NewsDeps(store=deps.news_store, bus=deps.bus))
