"""remove auth system (local single-user)

Revision ID: a1b2c3d4e5f6
Revises: 9dd51a4a165a
Create Date: 2026-08-09 12:00:00.000000

删除 refresh_tokens 表；合并多用户数据到本地学习者。
users.password_hash / token_version 因 SQLite DROP COLUMN 会损坏 UUID 亲和性而保留为遗留列。
本地学习者固定 ID 含字母（a000…），并以 SQLAlchemy UUID bind 格式（无连字符）写入，
避免纯数字 hex 被 SQLite 读成 INTEGER，也避免与 ORM 查询参数格式不一致。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9dd51a4a165a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 与 SQLAlchemy UUID(as_uuid=True) 在 SQLite 上的 bind 格式一致（无连字符）。
# 含字母 a，避免纯数字 hex 被 SQLite 读成 INTEGER。
LOCAL_ID = "a0000000000040008000000000000001"

_USER_FK_TABLES = (
    "projects",
    "notes",
    "categories",
    "tags",
    "agent_sessions",
)


def upgrade() -> None:
    conn = op.get_bind()

    op.drop_table("refresh_tokens")

    rows = conn.execute(sa.text("SELECT id FROM users ORDER BY created_at ASC")).fetchall()
    if not rows:
        return

    primary = str(rows[0][0])

    profiles = conn.execute(sa.text("SELECT user_id FROM user_profiles")).fetchall()
    profile_ids = {str(r[0]) for r in profiles}
    if primary not in profile_ids and profile_ids:
        src = next(iter(profile_ids))
        conn.execute(
            sa.text(
                "INSERT INTO user_profiles "
                "(user_id, tech_profile, preferences, goals, history_summary, agent_prefs, updated_at) "
                "SELECT :pid, tech_profile, preferences, goals, history_summary, agent_prefs, updated_at "
                "FROM user_profiles WHERE user_id = :src"
            ),
            {"pid": primary, "src": src},
        )
    for pid in profile_ids:
        if pid != primary:
            conn.execute(
                sa.text("DELETE FROM user_profiles WHERE user_id = :pid"),
                {"pid": pid},
            )

    for table in _USER_FK_TABLES:
        conn.execute(
            sa.text(f"UPDATE {table} SET user_id = :pid WHERE user_id != :pid"),
            {"pid": primary},
        )

    conn.execute(sa.text("DELETE FROM users WHERE id != :pid"), {"pid": primary})
    conn.execute(
        sa.text("UPDATE users SET username = 'local' WHERE id = :pid"),
        {"pid": primary},
    )

    if primary.replace("-", "").lower() != LOCAL_ID.replace("-", "").lower():
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        try:
            for table in _USER_FK_TABLES:
                conn.execute(
                    sa.text(f"UPDATE {table} SET user_id = :local WHERE user_id = :pid"),
                    {"local": LOCAL_ID, "pid": primary},
                )
            conn.execute(
                sa.text("UPDATE user_profiles SET user_id = :local WHERE user_id = :pid"),
                {"local": LOCAL_ID, "pid": primary},
            )
            conn.execute(
                sa.text("UPDATE users SET id = :local WHERE id = :pid"),
                {"local": LOCAL_ID, "pid": primary},
            )
        finally:
            conn.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("refresh_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_refresh_tokens_token_hash"), ["token_hash"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_refresh_tokens_user_id"), ["user_id"], unique=False
        )
