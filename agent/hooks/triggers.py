"""钩子点触发(§9.13):注册与发射。hook 异常隔离,不炸主流程。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

HOOK_POINTS = (
    "on_event",  # 领域事件到达
    "pre_tool",  # 工具调用前(可改写/拦截返回 False)
    "post_tool",  # 工具调用后
    "on_subagent_start",
    "on_subagent_end",
    "on_user_message",
)

HookFn = Callable[..., Awaitable[Any]]

log = logging.getLogger("agent.hooks")


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[str, list[tuple[str, HookFn]]] = {p: [] for p in HOOK_POINTS}
        # 声明式 hook 声明过的领域事件 pattern(保声明顺序,去重;phase-28):
        # 供 EventLoop 精确订阅;register("on_event") 的纯 Python 钩子不在此列
        self._event_patterns: list[str] = []

    def record_event_pattern(self, pattern: str) -> None:
        """Loader 包装 on_event 时登记领域事件类型(支持 fnmatch 通配),供订阅。"""
        if pattern not in self._event_patterns:
            self._event_patterns.append(pattern)

    @property
    def event_patterns(self) -> tuple[str, ...]:
        """声明式 hook 声明过的领域事件类型;生命周期点不记。"""
        return tuple(self._event_patterns)

    def register(self, point: str, fn: HookFn, *, source: str = "local") -> None:
        if point not in self._hooks:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT, f"未知钩子点: {point}(可选: {HOOK_POINTS})"
            )
        self._hooks[point].append((source, fn))

    async def fire(self, point: str, **kwargs: Any) -> list[Any]:
        """依次触发;单个 hook 失败只记日志。pre_tool 任一返回 False 表示拦截。"""
        results = []
        for source, fn in self._hooks.get(point, []):
            try:
                results.append(await fn(**kwargs))
            except Exception:  # hook 失败隔离
                log.exception("hook 失败(%s @ %s)", source, point)
        return results

    def registered(self) -> dict[str, int]:
        return {p: len(fns) for p, fns in self._hooks.items() if fns}
