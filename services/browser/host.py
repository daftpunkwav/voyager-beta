"""browser 宿主适配层(§8.7)。

本服务只下发指令、回收结果;真实浏览器由 desktop/browser-host 执行。
当前为骨架实现:记录调用并返回占位结果,接入 desktop 后替换为真实 IPC。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from platform_contracts import ErrorSuffix, ServiceError


@dataclass
class BrowserResult:
    """浏览器指令执行结果。"""

    ok: bool
    url: str
    title: str
    text: str
    screenshot_path: str
    error: str


async def navigate(session_id: str, url: str, *, headless: bool,
                   allowed_domains: list[str]) -> BrowserResult:
    """导航到 URL。"""
    _check_domain(url, allowed_domains)
    return BrowserResult(
        ok=True, url=url, title="placeholder", text="",
        screenshot_path="", error="",
    )


async def click(session_id: str, selector: str, *, allowed_domains: list[str]) -> BrowserResult:
    """点击元素。"""
    return BrowserResult(
        ok=True, url="", title="", text=f"clicked {selector}",
        screenshot_path="", error="",
    )


async def type_text(session_id: str, selector: str, text: str,
                    *, allowed_domains: list[str]) -> BrowserResult:
    """在元素中输入文本。"""
    return BrowserResult(
        ok=True, url="", title="", text=f"typed into {selector}",
        screenshot_path="", error="",
    )


async def read_page(session_id: str, *, allowed_domains: list[str]) -> BrowserResult:
    """读取当前页面文本。"""
    return BrowserResult(
        ok=True, url="", title="placeholder", text="page text placeholder",
        screenshot_path="", error="",
    )


async def screenshot(session_id: str, *, allowed_domains: list[str],
                     workspace_dir: str) -> BrowserResult:
    """截图并保存到 workspace/browser-screenshots/。"""
    return BrowserResult(
        ok=True, url="", title="", text="",
        screenshot_path=f"{workspace_dir}/browser-screenshots/{session_id}.png",
        error="",
    )


def _check_domain(url: str, allowed_domains: list[str]) -> None:
    if not allowed_domains:
        return
    netloc = urlparse(url).netloc
    if not any(netloc == d or netloc.endswith(f".{d}") for d in allowed_domains):
        raise ServiceError(
            "browser", ErrorSuffix.FORBIDDEN,
            f"域名不在白名单: {netloc}",
        )
