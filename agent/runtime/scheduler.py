"""调度:subagent 并发上限、命名任务跟踪、一次性定时器(§9.1 / §9.8 追问用)。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any


class Scheduler:
    """进程内调度器。subagent 不是微服务(§9.4.5):并发控制靠信号量。"""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent  # 观测用;不翻 Semaphore 私有属性
        self._tasks: dict[str, asyncio.Task] = {}
        self._timers: dict[str, asyncio.Task] = {}

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    async def run(self, name: str, coro: Awaitable[Any]) -> Any:
        """在并发上限内运行命名任务。"""
        async with self._sem:
            task = asyncio.current_task()
            if task is not None:
                self._tasks[name] = task
            try:
                return await coro
            finally:
                self._tasks.pop(name, None)

    def call_later(
        self, delay: float, fn: Callable[[], Awaitable[Any]], *, name: str = ""
    ) -> str:
        """一次性定时器(追问/提醒),返回 timer id 可取消。"""
        timer_id = name or uuid.uuid4().hex[:8]

        async def _fire() -> None:
            try:
                await asyncio.sleep(delay)
                await fn()
            finally:
                self._timers.pop(timer_id, None)

        self._timers[timer_id] = asyncio.create_task(_fire())
        return timer_id

    def cancel_timer(self, timer_id: str) -> bool:
        task = self._timers.pop(timer_id, None)
        if task is not None:
            task.cancel()
            return True
        return False

    def active(self) -> list[str]:
        return sorted(self._tasks)

    async def cancel(self, name: str) -> bool:
        task = self._tasks.pop(name, None)
        if task is not None:
            task.cancel()
            return True
        return False

    async def shutdown(self) -> None:
        for task in [*self._tasks.values(), *self._timers.values()]:
            task.cancel()
