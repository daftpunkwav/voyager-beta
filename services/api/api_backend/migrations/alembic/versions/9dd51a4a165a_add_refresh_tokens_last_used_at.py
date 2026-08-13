"""add refresh_tokens.last_used_at

§4.3.5 (D-06) refresh_tokens 缺最后使用时间列。新增 last_used_at；
调用 refresh 时更新该字段便于审计 / 清理过期。

Revision ID: 9dd51a4a165a
Revises: f4542a1f742b
Create Date: 2026-08-06 22:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9dd51a4a165a'
down_revision: Union[str, Sequence[str], None] = 'f4542a1f742b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'refresh_tokens',
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('refresh_tokens', 'last_used_at')