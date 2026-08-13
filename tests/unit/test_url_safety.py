"""出站 URL SSRF 校验单元测试"""
import ipaddress
import socket

import pytest
from api_backend.core.url_safety import (
    assert_safe_outbound_https_url,
    is_blocked_ip,
    validate_public_https_url,
)


def test_is_blocked_ip_private_and_link_local():
    assert is_blocked_ip(ipaddress.ip_address("10.0.0.1"))
    assert is_blocked_ip(ipaddress.ip_address("169.254.169.254"))
    assert is_blocked_ip(ipaddress.ip_address("127.0.0.1"))
    assert not is_blocked_ip(ipaddress.ip_address("1.1.1.1"))
    # fake-ip / RFC2544：代理 TUN 常用段，不得当作内网 SSRF 拦截
    assert not is_blocked_ip(ipaddress.ip_address("198.18.0.1"))
    assert not is_blocked_ip(ipaddress.ip_address("198.19.255.255"))


def test_validate_rejects_http_and_localhost():
    with pytest.raises(ValueError, match="https"):
        validate_public_https_url("http://api.openai.com/v1")
    with pytest.raises(ValueError, match="localhost"):
        validate_public_https_url("https://localhost/v1")


def test_validate_rejects_dns_to_private(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr("py_shared.security.url_safety.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="禁止"):
        validate_public_https_url("https://evil.example.com/v1")


def test_assert_safe_outbound_https_url_none():
    assert assert_safe_outbound_https_url(None) is None
    assert assert_safe_outbound_https_url("  ") is None


def test_assert_safe_outbound_allows_public(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]

    monkeypatch.setattr("py_shared.security.url_safety.socket.getaddrinfo", fake_getaddrinfo)
    url = "https://api.openai.com/v1"
    assert assert_safe_outbound_https_url(url) == url


def test_assert_safe_outbound_allows_fake_ip_dns(monkeypatch):
    """代理 fake-ip 将公网域名解析到 198.18.0.0/15 时应放行。"""

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.34", 0))]

    monkeypatch.setattr("py_shared.security.url_safety.socket.getaddrinfo", fake_getaddrinfo)
    url = "https://api.minimaxi.com/anthropic"
    assert assert_safe_outbound_https_url(url) == url


def test_llm_provider_blocks_unsafe_api_base(monkeypatch):
    """出站 kwargs 构建时若 base 解析到内网则 RuntimeError。"""
    from agent_core.llm.config import LLMConfig
    from agent_core.llm.provider import LLMProvider

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.9", 0))]

    monkeypatch.setattr("py_shared.security.url_safety.socket.getaddrinfo", fake_getaddrinfo)
    cfg = LLMConfig(
        provider="openai",
        model="gpt-4o",
        api_key="sk-test",
        api_base="https://evil.example.com/v1",
    )
    provider = LLMProvider(cfg)
    with pytest.raises(RuntimeError, match="LLM_API_BASE_BLOCKED"):
        provider._kwargs()
