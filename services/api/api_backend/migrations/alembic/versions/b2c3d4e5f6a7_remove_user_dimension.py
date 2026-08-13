"""remove user dimension (local single-machine)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-09 13:20:00.000000

彻底去掉 users / user_id 维度：
- 新建 app_state 单行表，从 users 迁移 settings / github / 展示字段
- user_profiles 改为整数 PK=1 的单例画像（无 FK）
- projects / notes / categories / tags / agent_sessions 去掉 user_id
- projects 唯一约束改为仅 url
- 删除 users 表

SQLite：建新表拷数据再 rename，避免 DROP COLUMN 损坏 UUID。
新表暂不写指向 `_new` 名的 FK（rename 后会失效）；数据拷贝期间 PRAGMA foreign_keys=OFF。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _swap(conn, old: str, new: str) -> None:
    """删除旧表并 rename 新表。"""
    op.drop_table(old)
    op.rename_table(new, old)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("PRAGMA foreign_keys=OFF"))

    # —— app_state ——
    op.create_table(
        "app_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False, server_default="local"),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("github_accounts", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "agent_permissions", sa.String(length=1024), nullable=False, server_default="{}"
        ),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    users = conn.execute(
        sa.text(
            "SELECT username, email, avatar_url, github_accounts, "
            "agent_permissions, settings_json, created_at "
            "FROM users ORDER BY created_at ASC"
        )
    ).fetchall()
    if users:
        u = users[0]
        conn.execute(
            sa.text(
                "INSERT INTO app_state "
                "(id, display_name, email, avatar_url, github_accounts, "
                "agent_permissions, settings_json, created_at) "
                "VALUES (1, :dn, :email, :avatar, :gh, :perms, :settings, :created)"
            ),
            {
                "dn": u[0] or "local",
                "email": u[1],
                "avatar": u[2],
                "gh": u[3] or "[]",
                "perms": u[4] or "{}",
                "settings": u[5] or "{}",
                "created": u[6],
            },
        )
    else:
        conn.execute(
            sa.text(
                "INSERT INTO app_state (id, display_name, github_accounts, "
                "agent_permissions, settings_json) "
                "VALUES (1, 'local', '[]', '{}', '{}')"
            )
        )

    # —— user_profiles 单例 ——
    op.create_table(
        "user_profiles_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tech_profile", sa.Text(), nullable=True),
        sa.Column("preferences", sa.Text(), nullable=True),
        sa.Column("goals", sa.Text(), nullable=True),
        sa.Column("history_summary", sa.Text(), nullable=True),
        sa.Column("agent_prefs", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    profiles = conn.execute(
        sa.text(
            "SELECT tech_profile, preferences, goals, history_summary, "
            "agent_prefs, updated_at FROM user_profiles"
        )
    ).fetchall()
    if profiles:
        p = profiles[0]
        conn.execute(
            sa.text(
                "INSERT INTO user_profiles_new "
                "(id, tech_profile, preferences, goals, history_summary, "
                "agent_prefs, updated_at) "
                "VALUES (1, :tp, :pref, :goals, :hs, :ap, :upd)"
            ),
            {
                "tp": p[0] or "{}",
                "pref": p[1] or "{}",
                "goals": p[2] or "[]",
                "hs": p[3] or "",
                "ap": p[4] or "{}",
                "upd": p[5],
            },
        )
    else:
        conn.execute(
            sa.text(
                "INSERT INTO user_profiles_new "
                "(id, tech_profile, preferences, goals, history_summary, agent_prefs) "
                "VALUES (1, '{}', '{}', '[]', '', '{}')"
            )
        )
    _swap(conn, "user_profiles", "user_profiles_new")

    # —— categories ——
    op.create_table(
        "categories_new",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("icon", sa.String(length=32), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("is_preset", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    conn.execute(
        sa.text(
            "INSERT INTO categories_new (id, name, icon, color, is_preset, created_at) "
            "SELECT id, name, icon, color, is_preset, created_at FROM categories"
        )
    )
    _swap(conn, "categories", "categories_new")

    # —— tags ——
    op.create_table(
        "tags_new",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    conn.execute(sa.text("INSERT INTO tags_new (id, name) SELECT id, name FROM tags"))
    _swap(conn, "tags", "tags_new")

    # —— projects（url 唯一，无 user_id）——
    # 若同一 url 多行（历史多用户），保留最早一行
    op.create_table(
        "projects_new",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("progress", sa.String(length=16), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("category_id", sa.CHAR(32), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_projects_url"),
    )
    conn.execute(
        sa.text(
            "INSERT INTO projects_new "
            "(id, name, url, description, stars, language, progress, source, "
            "note, category_id, imported_at, created_at, updated_at) "
            "SELECT id, name, url, description, stars, language, progress, source, "
            "note, category_id, imported_at, created_at, updated_at FROM projects "
            "WHERE id IN ("
            "  SELECT id FROM projects p1 WHERE NOT EXISTS ("
            "    SELECT 1 FROM projects p2 "
            "    WHERE p2.url = p1.url AND ("
            "      p2.created_at < p1.created_at OR "
            "      (p2.created_at = p1.created_at AND p2.id < p1.id)"
            "    )"
            "  )"
            ")"
        )
    )
    # 暂不 swap projects：notes / agent_sessions 仍引用旧表；先重建依赖表

    # —— notes ——
    op.create_table(
        "notes_new",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("project_id", sa.CHAR(32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    conn.execute(
        sa.text(
            "INSERT INTO notes_new (id, project_id, title, content, created_at, updated_at) "
            "SELECT n.id, n.project_id, n.title, n.content, n.created_at, n.updated_at "
            "FROM notes n "
            "INNER JOIN projects_new p ON p.id = n.project_id"
        )
    )
    _swap(conn, "notes", "notes_new")
    op.create_index("ix_notes_project_id", "notes", ["project_id"])

    # —— agent_sessions ——
    op.create_table(
        "agent_sessions_new",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("project_id", sa.CHAR(32), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("active_agent", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    conn.execute(
        sa.text(
            "INSERT INTO agent_sessions_new "
            "(id, title, project_id, source, active_agent, status, created_at, updated_at) "
            "SELECT s.id, s.title, "
            "CASE WHEN p.id IS NOT NULL THEN s.project_id ELSE NULL END, "
            "s.source, s.active_agent, s.status, s.created_at, s.updated_at "
            "FROM agent_sessions s "
            "LEFT JOIN projects_new p ON p.id = s.project_id"
        )
    )
    _swap(conn, "agent_sessions", "agent_sessions_new")
    op.create_index("ix_agent_sessions_project_id", "agent_sessions", ["project_id"])

    # 清理指向已丢弃项目的关联
    conn.execute(
        sa.text(
            "DELETE FROM project_tags WHERE project_id NOT IN (SELECT id FROM projects_new)"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM agent_session_projects WHERE project_id NOT IN (SELECT id FROM projects_new)"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM project_analyses WHERE project_id NOT IN (SELECT id FROM projects_new)"
        )
    )

    _swap(conn, "projects", "projects_new")
    op.create_index("ix_projects_category_id", "projects", ["category_id"])

    op.drop_table("users")

    conn.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    raise NotImplementedError("不可回退：user 维度已永久移除")
