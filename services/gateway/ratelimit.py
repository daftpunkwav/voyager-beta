"""入口限流(§7.5 第一层):每 actor 每分钟滑动窗口 + SSE 连接数上限。

纯内存计数(gateway 允许持有限流计数,§6.3);配置值由部署入口注入。
超限抛 GATEWAY.RATE_LIMITED(429),与能力层 CostQuota 的语义一致。
"""

from __future__ import annotations

import time
from collections import deque

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "gateway"


class RateLimiter:
    def __init__(self, per_minute: int = 600, sse_max: int = 8) -> None:
        self._per_minute = per_minute
        self._sse_max = sse_max
        self._hits: dict[str, deque[float]] = {}
        self._sse_open = 0

    def check(self, actor_id: str) -> None:
        now = time.time()
        hits = self._hits.setdefault(actor_id, deque())
        while hits and now - hits[0] > 60.0:
            hits.popleft()
        if len(hits) >= self._per_minute:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.RATE_LIMITED,
                f"请求过频: {actor_id} 每分钟上限 {self._per_minute}",
                hint="稍后重试;限额见设置 gateway.rate_limit.per_minute",
            )
        hits.append(now)

    def acquire_sse(self) -> None:
        if self._sse_open >= self._sse_max:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.RATE_LIMITED,
                f"SSE 连接数已达上限 {self._sse_max}",
                hint="关闭其他页面的流连接后重试",
            )
        self._sse_open += 1

    def release_sse(self) -> None:
        self._sse_open = max(0, self._sse_open - 1)

    @property
    def sse_open(self) -> int:
        return self._sse_open
