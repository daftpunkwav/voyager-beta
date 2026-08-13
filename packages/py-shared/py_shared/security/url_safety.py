"""出站 URL 安全校验 —— 防止 SSRF（含保存时与出站前二次 DNS 校验）"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Clash / Surge / mihomo 等 TUN 的 fake-ip 常用 198.18.0.0/15（RFC 2544）。
# Python ipaddress 会将其标为 is_private，但并非真实内网服务；一律拦截会导致
# 开启代理 fake-ip 的用户无法配置/调用任何自定义 LLM API Base（如 MiniMax）。
_FAKE_IP_OR_BENCHMARK_V4 = ipaddress.ip_network("198.18.0.0/15")


def is_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """判断解析后的 IP 是否属于 SSRF 高危范围。

    故意放行 198.18.0.0/15：无代理时该段通常不可达（失败安全），
    有 fake-ip 代理时则是正常出站路径。
    """
    if addr.version == 4 and addr in _FAKE_IP_OR_BENCHMARK_V4:
        return False
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_reserved
        or addr.is_link_local
        or addr.is_unspecified
        or addr.is_multicast
    )


def validate_public_https_url(
    url: str,
    *,
    resolve_dns: bool = True,
) -> str:
    """
    校验 URL 为可出站的公开 HTTPS 地址。

    失败时抛出 ValueError（消息供 schema / 调用方使用）。
    成功返回原 url（不改写）。
    """
    if not url or not str(url).strip():
        raise ValueError("URL 不能为空")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("API 基础地址必须是 https 协议")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("API 基础地址必须包含有效域名")
    if host in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("禁止指向 localhost")

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None

    if addr is not None and is_blocked_ip(addr):
        raise ValueError("禁止指向私有/链路本地/保留 IP")

    internal_suffixes = (".local", ".internal", ".lan", ".corp", ".home")
    if any(host.endswith(suffix) for suffix in internal_suffixes):
        raise ValueError("禁止指向内网域名")

    if addr is None and resolve_dns:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise ValueError("无法解析 API 基础地址域名") from exc
        if not infos:
            raise ValueError("无法解析 API 基础地址域名")
        seen: set[str] = set()
        for info in infos:
            ip_str = str(info[4][0])
            if ip_str in seen:
                continue
            seen.add(ip_str)
            try:
                resolved = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if is_blocked_ip(resolved):
                raise ValueError(
                    f"API 基础地址解析到禁止的内网/保留 IP（{host} → {ip_str}）"
                )
    return url.strip()


def assert_safe_outbound_https_url(url: str | None) -> str | None:
    """出站前二次校验；None 表示不使用自定义 base。"""
    if url is None or not str(url).strip():
        return None
    return validate_public_https_url(url, resolve_dns=True)
