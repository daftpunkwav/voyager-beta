"""HTTP 身份解析(§7.4):Bearer / Cookie;非法令牌失败关闭;无令牌仅环回降权。"""

from __future__ import annotations

import ipaddress

from platform_contracts import LOCAL_USER, ActorRef, ErrorSuffix, ServiceError

from platform_actor.token import LocalTokenIssuer

COOKIE_NAME = "local_session"
_DOMAIN = "actor"

# 非 IP 的环回别名;TestClient 的 ASGI client host 为 "testclient"
_LOOPBACK_NAMES = frozenset({"localhost", "testclient"})
_PUBLIC_PATHS = frozenset({"/health", "/api/session/bootstrap"})


def is_loopback(request) -> bool:
    """请求是否来自本机环回(含 Starlette TestClient 与 IPv4-mapped ::ffff:127.0.0.1)。"""
    client = getattr(request, "client", None)
    host = (client.host if client is not None else "") or ""
    if host in _LOOPBACK_NAMES:
        return True
    try:
        addr = ipaddress.ip_address(host)
        mapped = getattr(addr, "ipv4_mapped", None)
        return (mapped or addr).is_loopback
    except ValueError:
        return False


def is_public_path(path: str) -> bool:
    """无需令牌的探活/签发入口。"""
    return path in _PUBLIC_PATHS


def token_from_request(request) -> str | None:
    """优先 Authorization: Bearer,其次 HttpOnly Cookie。"""
    header = request.headers.get("authorization") or ""
    if header.startswith("Bearer "):
        token = header.removeprefix("Bearer ").strip()
        if token:
            return token
    cookies = getattr(request, "cookies", None)
    if cookies is not None:
        cookie = cookies.get(COOKIE_NAME)
        if cookie:
            return cookie
    return None


def resolve_http_actor(request, issuer: LocalTokenIssuer | None) -> ActorRef:
    """解析调用者。issuer 未装配时保持单用户本机语义;装配后非环回必须持令牌。"""
    if issuer is None:
        return LOCAL_USER
    token = token_from_request(request)
    if token:
        return issuer.verify(token)
    if is_loopback(request):
        return LOCAL_USER
    raise ServiceError(
        _DOMAIN,
        ErrorSuffix.AUTH_REQUIRED,
        "需要本机会话令牌",
        hint="从环回地址打开应用以签发会话,或携带 Authorization: Bearer",
    )
