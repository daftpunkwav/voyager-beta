"""add learner identity_json

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-09 14:00:00.000000

为本机学习者画像增加 identity_json（称呼、语言、技术栈等自填信息）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch:
        batch.add_column(
            sa.Column("identity_json", sa.Text(), nullable=True, server_default="{}")
        )


def downgrade() -> None:
    with op.batch_alter_table("user_profiles") as batch:
        batch.drop_column("identity_json")
