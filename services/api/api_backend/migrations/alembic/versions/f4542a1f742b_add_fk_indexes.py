"""add_fk_indexes

§4.1.8 (D-01 / S-21) 给所有外键列补 B-tree 索引，避免 user/project/session 维度
查询在大表上退化成全表扫描。

Revision ID: f4542a1f742b
Revises: e30c21e90eef
Create Date: 2026-08-06 21:50:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4542a1f742b'
down_revision: Union[str, Sequence[str], None] = 'e30c21e90eef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 需补索引的 (表, 列) 清单，与 models/*.py 一一对应
_INDEXES = [
    ('categories', 'user_id'),
    ('tags', 'user_id'),
    ('projects', 'user_id'),
    ('projects', 'category_id'),
    ('agent_sessions', 'user_id'),
    ('agent_sessions', 'project_id'),
    ('notes', 'user_id'),
    ('notes', 'project_id'),
    ('agent_messages', 'session_id'),
    ('project_analyses', 'project_id'),
]


def upgrade() -> None:
    for table, col in _INDEXES:
        op.create_index(
            f'ix_{table}_{col}',
            table,
            [col],
            unique=False,
        )
    # §4.1.9: 同一用户同一仓库 URL 必须唯一，防止并发导入竞态
    op.create_index(
        'uq_projects_user_url', 'projects', ['user_id', 'url'], unique=True
    )


def downgrade() -> None:
    op.drop_index('uq_projects_user_url', table_name='projects')
    for table, col in reversed(_INDEXES):
        op.drop_index(f'ix_{table}_{col}', table_name=table)