"""ĺćľďźčˇ¨ worker äźčŻćľĺćśäżĄĺˇďźÂ§4.1.1 / S-05ďźă"""

from __future__ import annotations

import datetime
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# čŽŠćľčŻĺŻéčż api_backend.* ä¸ agent_core.* č§Łć
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "services" / "agent"))
sys.path.insert(0, str(ROOT / "services" / "agent" / "agent_core"))


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """ćŻç¨äžçŹçŤ in-memory SQLite + Base.metadata.create_allă"""
    import api_backend.models  # noqa: F401
    from api_backend.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _create_session(db: AsyncSession) -> uuid.UUID:
    from api_backend.models.agent import AgentSession

    sid = uuid.uuid4()
    db.add(AgentSession(
        id=sid,
        title="t",
        project_id=None,
        source="chat",
        active_agent="hub",
        status="active",
        created_at=datetime.datetime.utcnow(),
        updated_at=None,
    ))
    await db.commit()
    return sid


@pytest.mark.asyncio
async def test_begin_returns_token(db: AsyncSession) -> None:
    from api_backend.core import stream_cancel

    sid = await _create_session(db)
    token1 = await stream_cancel.begin(db, sid)
    assert token1 and isinstance(token1, str)


@pytest.mark.asyncio
async def test_poll_returns_false_when_token_matches(db: AsyncSession) -> None:
    from api_backend.core import stream_cancel

    sid = await _create_session(db)
    token = await stream_cancel.begin(db, sid)
    assert await stream_cancel.poll(db, sid, token) is False


@pytest.mark.asyncio
async def test_begin_overrides_previous_token(db: AsyncSession) -> None:
    from api_backend.core import stream_cancel

    sid = await _create_session(db)
    old = await stream_cancel.begin(db, sid)
    new = await stream_cancel.begin(db, sid)
    assert old != new
    # old token ĺˇ˛ä¸ĺĺšé
    assert await stream_cancel.poll(db, sid, old) is True
    # new token äťä¸şčŞčşŤ
    assert await stream_cancel.poll(db, sid, new) is False


@pytest.mark.asyncio
async def test_clear_only_removes_own_token(db: AsyncSession) -> None:
    from api_backend.core import stream_cancel

    sid = await _create_session(db)
    token = await stream_cancel.begin(db, sid)
    # ç¨é token č° clearďźä¸ĺşĺ é¤
    await stream_cancel.clear(db, sid, "bogus_token_xyz")
    # čŞĺˇą token äťćć
    assert await stream_cancel.poll(db, sid, token) is False
    # ć­ŁçĄŽ clear ĺĺŻäťĽéć° begin
    await stream_cancel.clear(db, sid, token)
    again = await stream_cancel.begin(db, sid)
    assert again and again != token