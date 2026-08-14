"""news 子模块能力(§8.2):fetch_news / list_news / get_news / add_news / remove_news。"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError
from platform_eventbus import EventBus

from modules.news.store import NewsStore, html_to_text

_DOMAIN = "sources"
registry = Registry(_DOMAIN)


@dataclass
class NewsDeps:
    store: NewsStore
    bus: EventBus | None


_deps: NewsDeps | None = None


def init_deps(deps: NewsDeps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> NewsDeps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


@capability(registry, name="fetch_news", description="抓取 URL 存为新闻条目(摘要级正文)", cost=3)
async def fetch_news(url: str, title: str = "") -> dict:
    deps = _require_deps()
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        raise ServiceError(_DOMAIN, ErrorSuffix.UNAVAILABLE,
                           f"抓取失败: {type(exc).__name__}: {exc}") from exc
    page_title, text = html_to_text(resp.text)
    nid = deps.store.add({"title": title or page_title or url, "url": url,
                          "summary": text[:300], "content": text})
    if deps.bus is not None:
        from platform_contracts import ActorKind, ActorRef, Event
        await deps.bus.publish(Event(
            type="source.ready",
            actor=ActorRef(kind=ActorKind.SYSTEM, id="sources.news"),
            payload={"source_id": nid, "kind": "news", "title": title or page_title}))
    return deps.store.get(nid)


@capability(registry, name="add_news", description="手动登记一条资料(标题+内容)")
def add_news(title: str, content: str = "", url: str = "") -> dict:
    deps = _require_deps()
    nid = deps.store.add({"title": title, "url": url,
                          "summary": content[:300], "content": content})
    return deps.store.get(nid)


@capability(registry, name="list_news", description="新闻列表(摘要)")
def list_news(limit: int = 50) -> list[dict]:
    return _require_deps().store.list(limit)


@capability(registry, name="get_news", description="按需取新闻全文")
def get_news(news_id: str) -> dict:
    item = _require_deps().store.get(news_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"条目不存在: {news_id}")
    return item


@capability(registry, name="remove_news", description="删除新闻条目", reversible=False)
def remove_news(news_id: str) -> dict:
    deps = _require_deps()
    item = deps.store.get(news_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"条目不存在: {news_id}")
    deps.store.remove(news_id)
    return {"removed": news_id, "title": item["title"]}
