"""
自定义异常 —— 使用登记的报错码（见 error_codes / ERROR_CODES.md）。

共享版本依赖 fastapi.HTTPException：API 层可直接抛出并交由 FastAPI 转 HTTP 响应，
agent_core / graph_engine_runtime 等非 API 层也能以相同语义抛出，由宿主统一捕获。
"""
from typing import Optional

from fastapi import HTTPException, status

from py_shared.error_codes import VALIDATION_ERROR


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[list[dict]] = None,
    ):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "details": details},
        )


class NotFoundError(AppException):
    def __init__(self, message: str, code: str):
        """code 必须为资源专用码（如 PROJECT_NOT_FOUND），禁止泛化 NOT_FOUND。"""
        super().__init__(status.HTTP_404_NOT_FOUND, code, message)


class ConflictError(AppException):
    def __init__(self, message: str, code: str):
        """code 必须为冲突专用码（如 PROJECT_URL_DUPLICATE）。"""
        super().__init__(status.HTTP_409_CONFLICT, code, message)


class ValidationAppError(AppException):
    def __init__(self, details: list[dict] | None = None, message: str = "参数校验失败"):
        super().__init__(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            VALIDATION_ERROR,
            message,
            details,
        )


# 兼容旧名
ValidationError = ValidationAppError
