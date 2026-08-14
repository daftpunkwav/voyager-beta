"""统一错误构造助手(§7.10):服务侧抛错、agent 侧按码决策。"""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError


def unavailable(
    service: str,
    detail: str = "",
    *,
    hint: str = "稍后重试;若持续不可用,请在设置页查看服务状态",
    trace_id: str = "",
) -> ServiceError:
    """服务不可用(503)。domain 取服务名,如 graph → GRAPH.UNAVAILABLE。"""
    return ServiceError(
        service,
        ErrorSuffix.UNAVAILABLE,
        detail or f"{service} 服务不可用",
        hint=hint,
        trace_id=trace_id,
    )


def queue_full(
    service: str,
    detail: str = "",
    *,
    hint: str = "队列已满,请稍后再试",
    trace_id: str = "",
) -> ServiceError:
    """服务背压(429,§7.5):超限返回"稍后再试"而非堆积。"""
    return ServiceError(
        service,
        ErrorSuffix.QUEUE_FULL,
        detail or f"{service} 队列已满",
        hint=hint,
        trace_id=trace_id,
    )
