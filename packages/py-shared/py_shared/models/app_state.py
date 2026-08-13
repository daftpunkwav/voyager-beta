"""
ORM 模型 —— 本机应用状态（单行，无用户概念）

替代原 users 表上的 settings_json / github_accounts / agent_permissions / 展示字段。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from py_shared.database import Base

# 单行表固定主键
APP_STATE_ID = 1


class AppState(Base):
    """本机全局状态：设置、GitHub 账号、Agent 权限、展示信息。"""

    __tablename__ = "app_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=APP_STATE_ID)
    display_name: Mapped[str] = mapped_column(String(64), default="local", nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    github_accounts: Mapped[str] = mapped_column(Text, default="[]")
    agent_permissions: Mapped[str] = mapped_column(String(1024), default="{}")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=datetime.utcnow, nullable=True
    )
