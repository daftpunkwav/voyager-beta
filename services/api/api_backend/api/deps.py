"""依赖注入 —— 本地单机模式，仅提供数据库会话。"""
from collections.abc import AsyncIterator

from api_backend.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db() -> AsyncIterator[AsyncSession]:
    # AsyncSession.__aiter__ 在 SQLAlchemy 2.0 已移除，经 get_session 迭代器取值
    async for session in get_session():
        yield session
