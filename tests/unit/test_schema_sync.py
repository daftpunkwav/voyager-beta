"""Alembic 迁移冒烟：upgrade head 可在空库建表。"""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_creates_core_tables(tmp_path: Path):
    db_path = tmp_path / "alembic_smoke.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    # 清 Settings 缓存
    from api_backend.config import get_settings

    get_settings.cache_clear()

    from api_backend.config import REPO_ROOT

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    assert "app_state" in tables
    assert "users" not in tables
    assert "projects" in tables
    assert "agent_sessions" in tables
    assert "alembic_version" in tables
