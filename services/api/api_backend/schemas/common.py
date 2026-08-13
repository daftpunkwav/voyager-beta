"""
Pydantic schemas —— 通用响应格式
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[list[dict]] = None


class OkData(BaseModel):
    success: bool = True


class ErrorResponse(BaseModel):
    error: ErrorDetail


class DataResponse(BaseModel, Generic[T]):
    data: T
    meta: dict = Field(default_factory=dict)


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PaginatedResponse(BaseModel, Generic[T]):
    data: PaginatedData[T]
    meta: dict = Field(default_factory=dict)


# 兼容旧 ListResponse 调用方（逐步迁移）
class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class ListResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: PaginationMeta


class OkResponse(BaseModel):
    ok: bool = True
