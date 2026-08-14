"""统一错误码(§7.10)。

形态 `<域>.<码>`:域由服务名大写得到(如 GRAPH),码为本包定义的通用后缀。
错误体统一为 {"error": {"code", "message", "service", "hint", "trace_id"}}。
本包只定义"码"与映射,不定义任何领域的"域"。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorSuffix(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"  # 服务不可用
    QUEUE_FULL = "QUEUE_FULL"  # 队列满,稍后再试
    NOT_FOUND = "NOT_FOUND"
    AUTH_REQUIRED = "AUTH_REQUIRED"  # 未认证
    FORBIDDEN = "FORBIDDEN"  # 已认证但无权限
    RATE_LIMITED = "RATE_LIMITED"  # 限流/配额耗尽
    INVALID_INPUT = "INVALID_INPUT"
    CONFLICT = "CONFLICT"
    INTERNAL = "INTERNAL"


#: 错误码后缀 → HTTP 状态映射(§7.10)
HTTP_STATUS: dict[ErrorSuffix, int] = {
    ErrorSuffix.UNAVAILABLE: 503,
    ErrorSuffix.QUEUE_FULL: 429,
    ErrorSuffix.NOT_FOUND: 404,
    ErrorSuffix.AUTH_REQUIRED: 401,
    ErrorSuffix.FORBIDDEN: 403,
    ErrorSuffix.RATE_LIMITED: 429,
    ErrorSuffix.INVALID_INPUT: 400,
    ErrorSuffix.CONFLICT: 409,
    ErrorSuffix.INTERNAL: 500,
}


def make_code(domain: str, suffix: ErrorSuffix) -> str:
    """拼装错误码:make_code("graph", UNAVAILABLE) -> "GRAPH.UNAVAILABLE"。"""
    return f"{domain.strip().upper().replace('-', '_')}.{suffix.value}"


@dataclass(frozen=True)
class ErrorBody:
    code: str
    message: str
    service: str
    hint: str = ""  # 可行动的提示(如 "稍后在设置页重试")
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "service": self.service,
            "hint": self.hint,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True)
class ErrorEnvelope:
    error: ErrorBody

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error.to_dict()}


class ServiceError(Exception):
    """携带 ErrorBody 的异常:服务/框架在任意环节抛出,边界处映射为 HTTP 或 MCP 错误。"""

    def __init__(
        self,
        domain: str,
        suffix: ErrorSuffix,
        message: str,
        *,
        hint: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message)
        self.body = ErrorBody(
            code=make_code(domain, suffix),
            message=message,
            service=domain,
            hint=hint,
            trace_id=trace_id,
        )

    @property
    def http_status(self) -> int:
        suffix = self.body.code.rsplit(".", 1)[-1]
        try:
            return HTTP_STATUS[ErrorSuffix(suffix)]
        except ValueError:
            return 500

    def to_envelope(self) -> dict[str, Any]:
        return ErrorEnvelope(error=self.body).to_dict()
