"""settings 能力注册表(§8.8):主题三件套 + 通用 get/set/schema 聚合。

- 用户与 agent 共用同一组能力(LocalAuth:scopes 为空即放行);
- secret 项写保护由 platform SettingsStore 强制(非 user → FORBIDDEN,铁律 7),
  get_setting 对 secret 项也只回 has_value 不回值;
- set_theme / set_setting 落库后由 SettingsStore 自动发 settings.changed
  事件,web 端监听热切换。
"""

from __future__ import annotations

from dataclasses import dataclass

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError
from platform_settings import SettingsStore

from .settings import DEFS, THEMES

_DOMAIN = "settings"
registry = Registry(_DOMAIN)

_THEME_LABELS = {"dark": "深色", "light": "浅色", "system": "跟随系统"}


@dataclass
class Deps:
    store: SettingsStore


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _schema_item(key: str) -> dict:
    for item in _require_deps().store.list_schema():
        if item["key"] == key:
            return item
    raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"未知设置项: {key}")


@capability(registry, name="list_themes", description="可用主题列表", cost=1)
def list_themes() -> list[dict]:
    return [{"id": t, "label": _THEME_LABELS[t]} for t in THEMES]


@capability(registry, name="get_theme", description="当前外观设置(主题/字号/代码字体)", cost=1)
def get_theme() -> dict:
    store = _require_deps().store
    return {
        "theme": store.get("appearance.theme"),
        "font_scale": store.get("appearance.font_scale"),
        "code_font": store.get("appearance.code_font"),
    }


@capability(registry, name="set_theme", description="切换主题/字号/代码字体(可静默执行)", cost=1)
async def set_theme(theme: str | None = None, font_scale: float | None = None,
                    code_font: str | None = None, _actor: ActorRef = None) -> dict:
    if theme is None and font_scale is None and code_font is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "theme / font_scale / code_font 至少给一个")
    store = _require_deps().store
    actor = _actor or ActorRef(kind=ActorKind.SYSTEM, id="settings.service")
    if theme is not None:
        await store.set("appearance.theme", theme, actor)
    if font_scale is not None:
        await store.set("appearance.font_scale", font_scale, actor)
    if code_font is not None:
        await store.set("appearance.code_font", code_font, actor)
    return get_theme()


@capability(registry, name="get_settings", description="全部设置 schema 聚合(可按分组过滤)", cost=1)
def get_settings(module: str | None = None) -> list[dict]:
    items = _require_deps().store.list_schema()
    if module:
        items = [i for i in items if i["module"] == module]
    return items


@capability(registry, name="get_setting", description="读单个设置项(secret 项只回 has_value)", cost=1)
def get_setting(key: str) -> dict:
    return _schema_item(key)


@capability(registry, name="set_setting", description="写单个设置项(secret 项仅用户可写)", cost=1)
async def set_setting(key: str, value, _actor: ActorRef = None) -> dict:
    store = _require_deps().store
    actor = _actor or ActorRef(kind=ActorKind.SYSTEM, id="settings.service")
    await store.set(key, value, actor)  # 校验 + secret 写保护 + 变更事件由 store 保证
    return _schema_item(key)


__all__ = ["DEFS", "Deps", "init_deps", "registry"]
