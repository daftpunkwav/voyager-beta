"""llm_usage_events 增加缓存命中/未命中列

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-10 02:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_usage_events",
        sa.Column("prompt_cached_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "llm_usage_events",
        sa.Column("prompt_uncached_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    # 历史行：未命中 = 原 prompt_tokens（无命中明细）
    op.execute(
        """
        UPDATE llm_usage_events
        SET prompt_uncached_tokens = COALESCE(prompt_tokens, 0)
        WHERE prompt_uncached_tokens = 0
          AND COALESCE(prompt_tokens, 0) > 0
        """
    )


def downgrade() -> None:
    op.drop_column("llm_usage_events", "prompt_uncached_tokens")
    op.drop_column("llm_usage_events", "prompt_cached_tokens")
