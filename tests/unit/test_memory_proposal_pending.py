"""记忆提案：默认待确认，需用户 accept 后才写入"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_propose_then_accept_via_api(client: AsyncClient, auth_headers: dict):
    from agent_core.memory.service import MemoryService
    from api_backend.database import get_session_factory

    me = await client.get("/api/v1/user/me", headers=auth_headers)
    assert me.status_code == 200
    factory = get_session_factory()
    async with factory() as db:
        mem = MemoryService(db)
        out = await mem.propose_memory(
            agent_id="mentor",
            value="偏好源码走读",
            confidence=0.9,
            kind="long_memory",
            apply=False,
        )
        assert out["status"] == "pending"
        pid = out["id"]

    profile1 = await client.get("/api/v1/user/profile", headers=auth_headers)
    assert profile1.status_code == 200
    data1 = profile1.json()["data"]
    assert any(p["id"] == pid for p in data1.get("pending_memory_proposals") or [])
    assert all(
        m.get("content") != "偏好源码走读" for m in data1.get("memory_items") or []
    )

    acc = await client.post(
        f"/api/v1/user/profile/memory-proposals/{pid}/accept",
        headers=auth_headers,
    )
    assert acc.status_code == 200, acc.text
    data2 = acc.json()["data"]
    assert any(m.get("content") == "偏好源码走读" for m in data2.get("memory_items") or [])
    assert all(p["id"] != pid for p in data2.get("pending_memory_proposals") or [])


@pytest.mark.asyncio
async def test_reject_memory_proposal(client: AsyncClient, auth_headers: dict):
    from agent_core.memory.service import MemoryService
    from api_backend.database import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        mem = MemoryService(db)
        out = await mem.propose_memory(
            agent_id="scout",
            value="应被拒绝的提案",
            confidence=0.5,
            kind="long_memory",
            apply=False,
        )
        pid = out["id"]

    rej = await client.post(
        f"/api/v1/user/profile/memory-proposals/{pid}/reject",
        headers=auth_headers,
    )
    assert rej.status_code == 200, rej.text
    data = rej.json()["data"]
    assert all(p["id"] != pid for p in data.get("pending_memory_proposals") or [])
    assert all(
        m.get("content") != "应被拒绝的提案" for m in data.get("memory_items") or []
    )
