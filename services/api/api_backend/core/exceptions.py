"""
自定义异常 —— 已下沉 py-shared，此处 re-export 兼容既有 import。
"""
from py_shared.exceptions import (  # noqa: F401
    AppException,
    ConflictError,
    NotFoundError,
    ValidationAppError,
    ValidationError,
)
