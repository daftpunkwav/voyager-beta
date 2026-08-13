"""Agent API 集成测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agent_question_without_auth_still_works(client: AsyncClient):
    """本地单机：无 Authorization 亦可调用（校验由业务层处理）。"""
    res = await client.post(
        "/api/v1/agent/question",
        json={"session_id": "00000000-0000-0000-0000-000000000001", "question_id": "q1", "answers": {}},
    )
    # 无会话时应业务错误，而非 401
    assert res.status_code != 401


@pytest.mark.asyncio
async def test_agent_analyze_without_auth_not_401(client: AsyncClient):
    res = await client.post("/api/v1/agent/analyze/00000000-0000-0000-0000-000000000000")
    assert res.status_code != 401


@pytest.mark.asyncio
async def test_agent_analyze_accepts_agent_id(client: AsyncClient, auth_headers: dict, monkeypatch):
    """analyze 支持 agent_id，流式返回 thinking + 正文。"""
    create = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "acme/widget", "url": "https://github.com/acme/widget"},
    )
    assert create.status_code == 200
    project_id = create.json()["data"]["id"]

    async def fake_direct(*_a, **_k):
        from agent_core.agents.stream_events import format_sse

        yield format_sse("thinking", {"content": "plan…"})
        yield format_sse("text_delta", {"content": "分析完成"})
        yield format_sse("done", {"usage": {"tokens": 4}, "iterations": 1})

    monkeypatch.setattr(
        "api_backend.services.agent_service.HubService.handle_direct_agent",
        fake_direct,
    )

    res = await client.post(
        f"/api/v1/agent/analyze/{project_id}",
        headers=auth_headers,
        json={"agent_id": "navigator", "depth": "quick"},
    )
    assert res.status_code == 200
    body = res.text
    assert "event: thinking" in body or "thinking" in body
    assert "分析完成" in body


@pytest.mark.asyncio
async def test_agent_analyze_missing_project_returns_forbidden(client: AsyncClient, auth_headers: dict):
    """分析不存在的项目应 403（本地单机无多用户隔离）。"""
    res = await client.post(
        "/api/v1/agent/analyze/00000000-0000-0000-0000-000000000099",
        headers=auth_headers,
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_agent_sessions_and_profiles(client: AsyncClient, auth_headers: dict):
    create = await client.post("/api/v1/agent/sessions", headers=auth_headers)
    assert create.status_code == 200
    sid = create.json()["data"]["id"]

    listing = await client.get("/api/v1/agent/sessions", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()["data"]) >= 1

    detail = await client.get(f"/api/v1/agent/sessions/{sid}", headers=auth_headers)
    assert detail.status_code == 200

    profiles = await client.get("/api/v1/agent/profiles", headers=auth_headers)
    assert profiles.status_code == 200
    assert len(profiles.json()["data"]) >= 6

    perms = await client.get("/api/v1/agent/permissions", headers=auth_headers)
    assert perms.status_code == 200

    patched = await client.patch(
        "/api/v1/agent/permissions",
        headers=auth_headers,
        json={"allow_github_api": False, "max_iterations": 5},
    )
    assert patched.status_code == 200
    pdata = patched.json()["data"]
    assert pdata["allow_github_api"] is False
    assert pdata["max_iterations"] == 5
    # 未传字段保持默认
    assert pdata["allow_web_search"] is True

    again = await client.get("/api/v1/agent/permissions", headers=auth_headers)
    assert again.json()["data"]["allow_github_api"] is False

    bad = await client.patch(
        "/api/v1/agent/permissions",
        headers=auth_headers,
        json={"max_iterations": 0},
    )
    assert bad.status_code == 422

    ctx = await client.get(
        "/api/v1/agent/context-window",
        headers=auth_headers,
        params={"session_id": sid},
    )
    assert ctx.status_code == 200

    patch = await client.patch(
        f"/api/v1/agent/sessions/{sid}",
        headers=auth_headers,
        json={"active_agent": "scout", "title": "Scout 会话"},
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["agent"] == "scout"
    assert patch.json()["data"]["title"] == "Scout 会话"

    bad_agent = await client.patch(
        f"/api/v1/agent/sessions/{sid}",
        headers=auth_headers,
        json={"active_agent": "not-an-agent"},
    )
    assert bad_agent.status_code == 422

    delete = await client.delete(f"/api/v1/agent/sessions/{sid}", headers=auth_headers)
    assert delete.status_code == 200
