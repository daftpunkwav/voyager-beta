"""ORM —— LLM 用量事件（模块独立；失败不影响聊天）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from api_backend.database import Base
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class LlmUsageEvent(Base):
    __tablename__ = "llm_usage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_uncached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
