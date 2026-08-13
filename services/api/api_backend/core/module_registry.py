"""模块注册表 —— 记录各域模块的加载状态，支持故障隔离。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ModuleStatus:
    name: str
    loaded: bool = False
    error: str | None = None
    router: Any = None  # 加载成功时持有 router 对象


# 全局状态：模块名 → 状态
_MODULE_STATES: dict[str, ModuleStatus] = {}


def safe_load_router(name: str, loader: Callable[[], Any]) -> Any | None:
    """安全加载单个域的 router。失败则记录状态并返回 None，不抛异常。

    Args:
        name: 域名（如 "agent"、"graph"），用于状态登记与报错码
        loader: 返回 router 对象的无参 callable（通常用 lambda 延迟 import）
    Returns:
        router 对象；失败返回 None
    """
    try:
        router = loader()
        _MODULE_STATES[name] = ModuleStatus(name=name, loaded=True, router=router)
        return router
    except Exception as e:
        # 关键：捕获 import 期异常，不让它冒泡到 app 启动
        logger.exception("模块 %s 加载失败，已跳过: %s", name, e)
        _MODULE_STATES[name] = ModuleStatus(name=name, loaded=False, error=str(e))
        return None


def get_module_status(name: str) -> ModuleStatus | None:
    return _MODULE_STATES.get(name)


def all_module_statuses() -> list[ModuleStatus]:
    return list(_MODULE_STATES.values())


def is_module_available(name: str) -> bool:
    s = _MODULE_STATES.get(name)
    return s is not None and s.loaded
