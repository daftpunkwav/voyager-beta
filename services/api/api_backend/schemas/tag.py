"""Pydantic schemas —— 标签"""
from uuid import UUID

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class TagOut(BaseModel):
    id: UUID
    name: str
    count: int = 0


class SetProjectTagsBody(BaseModel):
    tag_ids: list[UUID] = Field(default_factory=list)


class SetProjectTagsOut(BaseModel):
    project_id: UUID
    tag_ids: list[UUID]
