"""
Pydantic schemas —— 分类相关请求/响应
"""
from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class CategoryUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
