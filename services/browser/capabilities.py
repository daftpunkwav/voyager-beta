"""browser 能力注册表(§8.7):navigate / click / type / read / screenshot。

真实浏览器由 desktop/browser-host 执行;本服务只下发指令、回收结果。
一切出网经网络权限层(§9.9)。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_capability import Registry, capability
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .host import click, navigate, read_page, screenshot, type_text
from .settings import DEFS
from .store import BrowserStore

_DOMAIN = "browser"
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    """服务运行时依赖。"""

    store: BrowserStore
    settings: SettingsStore
    bus: EventBus | None
    workspace: Path


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _allowed_domains() -> list[str]:
    return _require_deps().settings.get("browser.allowed_domains") or []


def _headless() -> bool:
    return _require_deps().settings.get("browser.headless")


def _session_dir() -> Path:
    deps = _require_deps()
    d = deps.workspace / "browser-sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _result_dict(result) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "url": result.url,
        "title": result.title,
        "text": result.text,
        "screenshot_path": result.screenshot_path,
        "error": result.error,
    }


@capability(registry, name="navigate",
            description="导航到 URL;域名受限时返回 FORBIDDEN")
async def navigate_url(url: str) -> dict[str, Any]:
    deps = _require_deps()
    sid = uuid.uuid4().hex[:12]
    deps.store.touch(sid, url)
    result = await navigate(sid, url, headless=_headless(),
                            allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="click", description="点击页面元素(CSS selector)")
async def click_element(session_id: str, selector: str) -> dict[str, Any]:
    _require_deps().store.touch(session_id)
    result = await click(session_id, selector, allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="type", description="在元素中输入文本")
async def type_element(session_id: str, selector: str, text: str) -> dict[str, Any]:
    _require_deps().store.touch(session_id)
    result = await type_text(session_id, selector, text,
                             allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="read", description="读取当前页面可见文本")
async def read(session_id: str) -> dict[str, Any]:
    _require_deps().store.touch(session_id)
    result = await read_page(session_id, allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="screenshot", description="截图并返回保存路径")
async def take_screenshot(session_id: str) -> dict[str, Any]:
    deps = _require_deps()
    deps.store.touch(session_id)
    result = await screenshot(session_id, allowed_domains=_allowed_domains(),
                              workspace_dir=str(deps.workspace))
    return _result_dict(result)


__all__ = ["DEFS", "Deps", "init_deps", "registry"]
