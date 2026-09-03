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
        # pattern → 声明过它的已装载 source 集合(phase-78):用户 hooks 热重载
        # 判定「除用户侧外是否还有插件需要该订阅」用;只随 record/forget 增删
        self._pattern_owners: dict[str, set[str]] = {}

    def record_event_pattern(self, pattern: str, source: str = "") -> None:
        """Loader 包装 on_event 时登记领域事件类型(支持 fnmatch 通配),供订阅。

        source 非空时同时记归属(phase-78):同一 pattern 可由用户 hooks 与
        多个插件共同声明,热卸一方时据此判定订阅是否仍被别人需要。
        """
        if pattern not in self._event_patterns:
            self._event_patterns.append(pattern)
        if source:
            self._pattern_owners.setdefault(pattern, set()).add(source)

    def forget_event_pattern(self, pattern: str) -> None:
        """撤销插件批准时撤回其声明的事件订阅(不存在的 pattern 是空操作)。"""
        if pattern in self._event_patterns:
            self._event_patterns.remove(pattern)
        self._pattern_owners.pop(pattern, None)

    @property
    def event_patterns(self) -> tuple[str, ...]:
        """声明式 hook 声明过的领域事件类型;生命周期点不记。"""
        return tuple(self._event_patterns)

    def pattern_owner_sources(self, pattern: str) -> tuple[str, ...]:
        """声明过该 pattern 的已装载 source(排序稳定;未声明 → 空)。"""
        return tuple(sorted(self._pattern_owners.get(pattern, ())))

    @property
    def sources(self) -> tuple[str, ...]:
        """当前注册过的全部 source(去重保序;list_user_hooks 判定已装载用)。"""
        seen: dict[str, None] = {}
        for entries in self._hooks.values():
            for source, _fn in entries:
                seen.setdefault(source, None)
        return tuple(seen)

    def register(self, point: str, fn: HookFn, *, source: str = "local") -> None:
        if point not in self._hooks:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT, f"未知钩子点: {point}(可选: {HOOK_POINTS})"
            )
        self._hooks[point].append((source, fn))

    def remove_source(self, prefix: str) -> int:
        """按 source 前缀移除注册(插件热卸,phase-72);返回移除数。"""
        removed = 0
        for point, entries in self._hooks.items():
            kept = [(s, fn) for s, fn in entries if not s.startswith(prefix)]
            removed += len(entries) - len(kept)
            self._hooks[point] = kept
        return removed

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
