"""ORM —— 代码图谱索引状态（本地单机，无 user 维度）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from py_shared.database import Base


class GraphIndexStatus(Base):
    """projects.id ↔ 引擎 project 名 ↔ 本地缓存路径 ↔ 索引状态。"""

    __tablename__ = "graph_index_status"
    __table_args__ = (UniqueConstraint("project_id", name="uq_graph_index_project"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    engine_project: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    local_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    head_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # NONE/QUEUED/CLONING/INDEXING/READY/STALE/CLONE_FAILED/INDEX_FAILED
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NONE")
    # fast/moderate/full
    index_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="moderate")
    node_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    edge_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=datetime.utcnow, nullable=True
    )
