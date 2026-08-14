"""容错(§9.17):重试/backoff/熔断;checkpoint 恢复见 state.py。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


async def with_retry(
    fn: Callable[[], Awaitable[Any]],
    *,
    retries: int = 2,
    backoff: float = 0.1,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> Any:
    """指数退避重试。最后一次失败原样抛出,由上层按错误码决策(§7.10)。"""
    delay = backoff
    for attempt in range(retries + 1):
        try:
            return await fn()
        except retry_on:
            if attempt >= retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """熔断器:连续失败 open_after 次则断开 reset_after 秒(半开自动试探)。"""

    def __init__(self, *, open_after: int = 3, reset_after: float = 30.0) -> None:
        self._open_after = open_after
        self._reset_after = reset_after
        self._failures = 0
        self._opened_at = 0.0

    @property
    def open(self) -> bool:
        if self._opened_at and time.time() - self._opened_at >= self._reset_after:
            return False  # 半开:放行一次试探
        return self._opened_at > 0

    async def call(self, fn: Callable[[], Awaitable[Any]]) -> Any:
        if self.open:
            raise CircuitOpenError("熔断中,稍后重试")
        try:
            result = await fn()
        except Exception:
            self._failures += 1
            if self._failures >= self._open_after:
                self._opened_at = time.time()
            raise
        self._failures = 0
        self._opened_at = 0.0
        return result
