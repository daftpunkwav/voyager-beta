"""add_agent_session_cancel_tokens

Revision ID: e30c21e90eef
Revises: 6096bed38e20
Create Date: 2026-08-06 21:36:00.000000

§4.1.1 (S-05) 跨 worker 会话流取消信号。
- 引入 `agent_session_cancel_tokens` 表（每会话至多一行）。
- 同会话新流会覆盖旧 token；旧流每 N 个 chunk 轮询一次，发现自身 token 失效即让步终止。
- 兼容单 worker 部署（已删除的 _begin_session_stream/_end_session_stream 保留为同进程 Event 快路径）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e30c21e90eef'
down_revision: Union[str, Sequence[str], None] = '6096bed38e20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_session_cancel_tokens',
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('cancel_token', sa.String(length=64), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('session_id'),
    )


def downgrade() -> None:
    op.drop_table('agent_session_cancel_tokens')
