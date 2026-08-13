"""Agent SSE 端点限流验证（审查报告 §1.2）"""
import uuid

import api_backend.api.agent as agent_api
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agent_chat_rate_limited_after_burst(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """同一用户高频调用 /agent/sessions/{id}/chat：第 21 次返回 429。"""
    # conftest 默认 RATE_LIMIT_ENABLED=false（其余测试不受限流影响）；
    # 本测试显式启用并按用户计数清零
    monkeypatch.setattr(agent_api.limiter, "enabled", True)
    agent_api.limiter.reset()

    # 打桩 stream_chat，避免真实 LLM 调用
    async def fake_stream_chat(db, user, session_id, message, project_id=None):
        yield 'event: done\ndata: {"usage": {"tokens": 0}}\n\n'

    monkeypatch.setattr(
        "api_backend.services.agent_service.stream_chat", fake_stream_chat
    )

    sid = uuid.uuid4()
    statuses = []
    for _ in range(21):
        res = await client.post(
            f"/api/v1/agent/sessions/{sid}/chat",
            headers=auth_headers,
            json={"message": "你好"},
        )
        statuses.append(res.status_code)

    assert statuses[:20] == [200] * 20
    assert statuses[-1] == 429
