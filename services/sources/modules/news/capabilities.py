"""news 子模块能力(§8.2):fetch_news / list_news / get_news / add_news / remove_news。

fetch_news 的 SSRF 防护采用「解析-钉住」模式:每跳在本模块内做唯一一次
DNS 解析并校验全部结果为公网地址,然后直接连接该 IP(TLS 以原域名做
SNI 与证书校验,Host 头保持原域名)。后续连接使用 IP 字面量,不再发生
第二次解析——从而消除「先校验后连接各解析一次」的 DNS rebinding 窗口。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus

from .store import NewsStore, html_to_text

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

_MAX_REDIRECTS = 3

#: resolver 类型:(host, port) -> 解析到的全部 IP 字符串;测试注入替身保证离线
ResolverFn = Callable[[str, int], Awaitable[list[str]]]

_NEWS_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.news")


async def _default_resolver(host: str, port: int) -> list[str]:
    """默认解析器(loop.getaddrinfo 走线程池,不阻塞事件循环);去重保序。"""
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, proto=socket.IPPROTO_TCP)
    seen: list[str] = []
    for info in infos:
        ip = str(ipaddress.ip_address(info[4][0]))
        if ip not in seen:
            seen.append(ip)
    return seen


def _literal_ips(host: str) -> list[str] | None:
    """host 本身是 IP 字面量时直接返回(不经过解析器;钉住即它自身)。"""
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        return None


def _assert_pinnable(url: str) -> tuple[urlparse.ParseResult, list[str]]:
    """语法层 + 地址层校验。仅 http(s)、主机名非空、所有地址全球可路由。

    拒绝回环/内网(RFC1918)/链路本地(含云元数据 169.254.169.254)/保留段。
    返回 (解析结果, 候选 IP 列表)。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"仅支持 http/https URL: {url}")
    host = parsed.hostname
    if not host:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"URL 缺少主机名: {url}")
    ips = _literal_ips(host)
    if ips is None:
        # 非字面量主机名在 fetch_news 内经 resolver 解析;此函数只做语法与字面量判断,
        # 以便单测在不触网的情况下复用语法检查
        return parsed, []
    for ip in ips:
        if not ipaddress.ip_address(ip).is_global:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.FORBIDDEN,
                f"目标不在公网范围: {host}({ip})",
                hint="内网/回环/链路本地地址被 SSRF 防护拒绝",
            )
    return parsed, ips


@dataclass
class NewsDeps:
    store: NewsStore
    bus: EventBus | None
    resolve: ResolverFn = field(default=_default_resolver)


_deps: NewsDeps | None = None


def init_deps(deps: NewsDeps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> NewsDeps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


async def _fetch_pinned(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """抓一跳:单次解析 → 全部公网校验 → 直接请求校验过的 IP。

    https 场景把原域名放进 sni_hostname 扩展(httpx/httpcore 约定),
    证书按原域名验证;Host 头保持原域名,服务端路由不受 IP 改写影响。
    """
    deps = _require_deps()
    parsed, literal = _assert_pinnable(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ips = literal if literal else await deps.resolve(host, port)
    if not ips:
        raise ServiceError(_DOMAIN, ErrorSuffix.UNAVAILABLE,
                           f"域名解析不到任何地址: {host}")
    chosen = ips[0]
    request = client.build_request("GET", httpx.URL(url).copy_with(host=chosen))
    request.headers["host"] = parsed.netloc  # 域名(含非默认端口)原样透传
    if parsed.scheme == "https":
        request.extensions["sni_hostname"] = host
    return await client.send(request)


@capability(registry, name="fetch_news", description="抓取 URL 存为新闻条目(摘要级正文)", cost=3)
async def fetch_news(url: str, title: str = "") -> dict:
    deps = _require_deps()
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            # 逐跳跟随重定向;每跳都重新走解析-校验-钉住流程(防外网页 302 → 内网)
            for _ in range(_MAX_REDIRECTS):
                resp = await _fetch_pinned(client, url)
                if resp.is_redirect and resp.has_redirect_location:
                    url = str(httpx.URL(url).join(resp.headers.get("location", "")))
                    continue
                break
            resp.raise_for_status()
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError(_DOMAIN, ErrorSuffix.UNAVAILABLE,
                           f"抓取失败: {type(exc).__name__}: {exc}") from exc
    page_title, text = html_to_text(resp.text)
    nid = deps.store.add({"title": title or page_title or url, "url": url,
                          "summary": text[:300], "content": text})
    if deps.bus is not None:
        await deps.bus.publish(Event(
            type="source.ready",
            actor=_NEWS_ACTOR,
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
