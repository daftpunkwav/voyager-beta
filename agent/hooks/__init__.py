"""hook 体系:注册/触发(triggers)+ 声明式加载(loader)。"""

from agent.hooks.loader import HookLoader
from agent.hooks.triggers import HOOK_POINTS, HookRegistry

__all__ = ["HOOK_POINTS", "HookLoader", "HookRegistry"]
