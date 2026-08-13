"""
数据库引擎与会话管理 —— SQLAlchemy 2.0 async
"""
from collections.abc import AsyncIterator
from pathlib import Path

from api_backend.config import get_settings
from py_shared.database import Base  # noqa: F401
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _async_database_url(url: str) -> str:
    """将同步 SQLite URL 转为 aiosqlite 异步 URL。"""
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url.removeprefix("sqlite:///")
    return url


def _ensure_data_dir(url: str) -> None:
    path = url.replace("sqlite:///", "")
    if path and not path.startswith(":"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _ensure_data_dir(settings.database_url)
        connect_args: dict = {}
        url = _async_database_url(settings.database_url)
        if url.startswith("sqlite"):
            # 多 worker 并行写状态时降低 database is locked
            connect_args["timeout"] = 30
        _engine = create_async_engine(
            url,
            echo=settings.debug,
            future=True,
            connect_args=connect_args,
        )
        if url.startswith("sqlite"):
            from sqlalchemy import event

            @event.listens_for(_engine.sync_engine, "connect")
            def _sqlite_on_connect(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


def reset_database() -> None:
    """测试专用：重置引擎与会话工厂。"""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends 用会话生成器"""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """应用启动时执行 Alembic upgrade 至 head（替代 create_all + schema_sync）。"""
    import asyncio

    import api_backend.models  # noqa: F401 — 注册 ORM metadata 供 Alembic 环境使用

    await asyncio.to_thread(_run_alembic_upgrade)


def _run_alembic_upgrade() -> None:
    """同步执行 alembic upgrade head（在线程中调用以免阻塞事件循环）。"""
    from alembic import command
    from alembic.config import Config
    from api_backend.config import REPO_ROOT

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    # 确保使用当前 Settings 的 database_url（env.py 也会读 Settings）
    command.upgrade(cfg, "head")

