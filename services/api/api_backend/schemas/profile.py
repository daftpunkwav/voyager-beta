"""Pydantic schemas —— 学习者画像（本机信息 + Agent 记忆）"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GoalOut(BaseModel):
    title: str
    deadline: Optional[str] = None
    priority: int = 1
    status: Literal["active", "completed", "paused"] = "active"


class MemoryItemOut(BaseModel):
    id: str
    category: Literal["summary", "goal", "tech", "preference"]
    content: str
    created_at: str
    updated_at: Optional[str] = None


class MemoryProposalOut(BaseModel):
    """待用户确认的 Agent 记忆提案"""

    id: str
    kind: Literal["long_memory", "profile_tech", "preference"] = "long_memory"
    value: str
    confidence: float = 0.7
    agent_id: str = "hub"
    evidence: list[str] = Field(default_factory=list)
    at: str = ""


class LearnerIdentityOut(BaseModel):
    """本机学习者主动填写的身份信息（供 Agent 按需读取）。"""

    preferred_name: str = Field(default="", max_length=64, description="Agent 称呼")
    spoken_languages: list[str] = Field(
        default_factory=list, description="熟练的自然语言，如 中文 / English"
    )
    programming_languages: list[str] = Field(
        default_factory=list, description="熟练的编程语言"
    )
    tech_stack: list[str] = Field(
        default_factory=list, description="常用框架 / 工具 / 技术栈"
    )
    interests: list[str] = Field(default_factory=list, description="学习兴趣与方向")
    occupation: str = Field(default="", max_length=64, description="身份或职业")
    experience_level: Literal["", "beginner", "intermediate", "advanced"] = Field(
        default="", description="整体经验水平"
    )
    bio: str = Field(default="", max_length=500, description="一句话简介")


class LearnerIdentityUpdate(BaseModel):
    preferred_name: Optional[str] = Field(default=None, max_length=64)
    spoken_languages: Optional[list[str]] = None
    programming_languages: Optional[list[str]] = None
    tech_stack: Optional[list[str]] = None
    interests: Optional[list[str]] = None
    occupation: Optional[str] = Field(default=None, max_length=64)
    experience_level: Optional[Literal["", "beginner", "intermediate", "advanced"]] = None
    bio: Optional[str] = Field(default=None, max_length=500)


class UserProfileOut(BaseModel):
    identity: LearnerIdentityOut = Field(default_factory=LearnerIdentityOut)
    tech_proficiency: dict[str, Any] = Field(default_factory=dict)
    learning_preferences: dict[str, Any] = Field(default_factory=dict)
    goals: list[GoalOut] = Field(default_factory=list)
    history_summary: str = ""
    memory_items: list[MemoryItemOut] = Field(default_factory=list)
    pending_memory_proposals: list[MemoryProposalOut] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)


class UserProfileUpdate(BaseModel):
    identity: Optional[LearnerIdentityUpdate] = None
    tech_proficiency: Optional[dict[str, Any]] = None
    learning_preferences: Optional[dict[str, Any]] = None
    goals: Optional[list[GoalOut]] = None
    history_summary: Optional[str] = None
    memory_items: Optional[list[MemoryItemOut]] = None
    extensions: Optional[dict[str, Any]] = None
