"""web 子模块能力(§8.2):网址剪藏(抓取/手动录入)/ 列表 / 元数据 / 删除。

save_url 的 SSRF 防护沿用 news 的「解析-钉住」模式:每跳在本模块内做唯一一次
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

from .store import WebStore, html_to_text, valid_tag

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

_MAX_REDIRECTS = 3

#: resolver 类型:(host, port) -> 解析到的全部 IP 字符串;测试注入替身保证离线
ResolverFn = Callable[[str, int], Awaitable[list[str]]]

_WEB_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.web")


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


def _as_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """解析 IP;IPv4-mapped IPv6(::ffff:127.0.0.1)还原为 v4 再判断。"""
    addr = ipaddress.ip_address(value)
    mapped = getattr(addr, "ipv4_mapped", None)
    return mapped if mapped is not None else addr


def _is_global_ip(value: str) -> bool:
    try:
        return _as_ip(value).is_global
    except ValueError:
        return False


def _literal_ips(host: str) -> list[str] | None:
    """host 本身是 IP 字面量时直接返回(不经过解析器;钉住即它自身)。"""
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        return None


def _reject_nonglobal(host: str, ips: list[str]) -> None:
    """任一候选非公网即拒绝(双栈里混入环回/链路本地视为 DNS rebinding)。"""
    for ip in ips:
        if not _is_global_ip(ip):
            raise ServiceError(
                _DOMAIN, ErrorSuffix.FORBIDDEN,
                f"目标不在公网范围: {host}({ip})",
                hint="内网/回环/链路本地地址被 SSRF 防护拒绝",
            )


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
        # 非字面量主机名在 save_url 内经 resolver 解析;此函数只做语法与字面量判断,
        # 以便单测在不触网的情况下复用语法检查
        return parsed, []
    _reject_nonglobal(host, ips)
    return parsed, ips


@dataclass
class WebDeps:
    store: WebStore
    bus: EventBus | None
    resolve: ResolverFn = field(default_factory=lambda: _default_resolver)


_deps: WebDeps | None = None


def init_deps(deps: WebDeps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> WebDeps:
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
    _reject_nonglobal(host, ips)
    chosen = ips[0]
    request = client.build_request("GET", httpx.URL(url).copy_with(host=chosen))
    request.headers["host"] = parsed.netloc  # 域名(含非默认端口)原样透传
    if parsed.scheme == "https":
        request.extensions["sni_hostname"] = host
    return await client.send(request)


@capability(registry, name="save_url",
            description="抓取网页正文并存入资料库(逐跳 DNS 钉住式 SSRF 防护)",
            cost=3)
async def save_url(url: str, title: str = "", tags: list[str] | None = None,
                   category: str = "") -> dict:
    deps = _require_deps()
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                               f"标签不合法: {tag}(≤32 字,禁 \\\"\\',[] 字符)")
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
    page_title, text, images = html_to_text(resp.text)
    domain = urlparse(url).hostname or ""
    final_title = title.strip() or page_title or url
    pid = deps.store.add({
        "title": final_title[:200], "url": url, "domain": domain,
        "summary": text[:300], "content": text,
        "tags": list(tags or []), "category": category,
        "meta": {"images": images, "chars": len(text)},
    })
    if deps.bus is not None:
        await deps.bus.publish(Event(
            type="source.added", actor=_WEB_ACTOR,
            payload={"source_id": pid, "kind": "web", "title": final_title}))
        await deps.bus.publish(Event(
            type="source.ready", actor=_WEB_ACTOR,
            payload={"source_id": pid, "kind": "web", "title": final_title}))
    return deps.store.get(pid)


@capability(registry, name="add_page",
            description="手动录入网页剪藏(标题+正文;抓取用 save_url)")
async def add_page(title: str, content: str = "", url: str = "",
                   tags: list[str] | None = None, category: str = "") -> dict:
    deps = _require_deps()
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"标签不合法: {tag}")
    domain = urlparse(url).hostname or "" if url else ""
    pid = deps.store.add({
        "title": title[:200], "url": url, "domain": domain,
        "summary": content[:300], "content": content,
        "tags": list(tags or []), "category": category,
        "meta": {"chars": len(content)},
    })
    if deps.bus is not None:
        await deps.bus.publish(Event(
            type="source.added", actor=_WEB_ACTOR,
            payload={"source_id": pid, "kind": "web", "title": title}))
    return deps.store.get(pid)


@capability(registry, name="list_pages",
            description="网页列表(摘要;query 命中标题/正文,tag 过滤)")
def list_pages(query: str = "", tag: str = "", limit: int = 50) -> list[dict]:
    return _require_deps().store.list(query=query.strip(), tag=tag.strip(),
                                      limit=limit)


@capability(registry, name="get_page", description="按需取网页全文")
def get_page(page_id: str) -> dict:
    item = _require_deps().store.get(page_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"网页不存在: {page_id}")
    return item


@capability(registry, name="set_page_meta",
            description="设置网页标题/标签/分类(与 set_repo_meta 对齐)")
def set_page_meta(page_id: str, title: str | None = None,
                  tags: list[str] | None = None,
                  category: str | None = None) -> dict:
    deps = _require_deps()
    item = deps.store.get(page_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"网页不存在: {page_id}")
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"标签不合法: {tag}")
    deps.store.set_meta(page_id, title=title, tags=tags, category=category)
    return deps.store.get(page_id)


@capability(registry, name="remove_page", description="删除网页剪藏",
            reversible=False)
async def remove_page(page_id: str) -> dict:
    deps = _require_deps()
    item = deps.store.get(page_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"网页不存在: {page_id}")
    deps.store.remove(page_id)
    if deps.bus is not None:
        await deps.bus.publish(Event(
            type="source.removed", actor=_WEB_ACTOR,
            payload={"source_id": page_id, "kind": "web", "title": item["title"]}))
    return {"removed": page_id, "title": item["title"]}
