"""迁移冒烟：upgrade head；不可回退的 remove_user_dimension 不参与 base 往返。"""
import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config


def _make_alembic_config(db_path: str) -> Config:
    """构造指向临时 SQLite 的 alembic config。"""
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini") )
    cfg.set_main_option("script_location", "services/api/api_backend/migrations/alembic")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    return cfg


def test_migration_upgrade_downgrade_roundtrip():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = _make_alembic_config(db_path)
        # head 含不可回退的 b2c3d4e5f6a7；先验证升级结果
        command.upgrade(cfg, "head")
        from sqlalchemy import create_engine, text

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            tables = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
                )
            ).fetchall()
            table_names = {t[0] for t in tables}
            for name in (
                "app_state",
                "projects",
                "agent_sessions",
                "agent_session_cancel_tokens",
            ):
                assert name in table_names, f"missing table {name} after upgrade"
            assert "users" not in table_names
            assert "refresh_tokens" not in table_names
        engine.dispose()

        # 更早迁移链（止于 a1）仍可 base 往返
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f2:
            db_path2 = f2.name
        try:
            cfg2 = _make_alembic_config(db_path2)
            command.upgrade(cfg2, "a1b2c3d4e5f6")
            command.downgrade(cfg2, "base")
            command.upgrade(cfg2, "a1b2c3d4e5f6")
        finally:
            import time

            time.sleep(0.1)
            try:
                Path(db_path2).unlink(missing_ok=True)
            except OSError:
                pass
    finally:
        import time

        time.sleep(0.1)
        try:
            Path(db_path).unlink(missing_ok=True)
        except OSError:
            pass
