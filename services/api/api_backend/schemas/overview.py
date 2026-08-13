"""Pydantic schemas —— 总览聚合数据"""
from typing import Literal, Optional

from pydantic import BaseModel

AgentIdLiteral = Literal["hub", "scout", "mentor", "navigator", "curator", "scribe"]


class ActivityItemOut(BaseModel):
    id: str
    type: Literal["import", "note", "agent", "progress"]
    title: str
    description: str
    created_at: str
    project_id: Optional[str] = None


class RecommendedProjectOut(BaseModel):
    id: str
    project_id: str
    name: str
    url: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int = 0
    reason: str
    recommended_by: AgentIdLiteral = "navigator"


class OverviewRecentNoteOut(BaseModel):
    id: str
    project_id: str
    project_name: str
    title: str
    updated_at: str


class TrendingRepoOut(BaseModel):
    owner: str
    repo: str
    url: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int = 0
    stars_today: Optional[int] = None
    rank: Optional[int] = None
