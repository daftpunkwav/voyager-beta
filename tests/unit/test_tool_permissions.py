"""工具执行时 agent_permissions 校验"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agent_core.tools.registry import ToolDefinition, ToolRegistry


@pytest.mark.asyncio
async def test_execute_blocks_github_when_permission_denied():
    reg = ToolRegistry()

    async def handler(**kwargs):
        return {"ok": True}

    reg.register(
        ToolDefinition(
            name="fetch_github_repo",
            description="t",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            allowed_agents=["scout"],
            required_permission="allow_github_api",
        )
    )
    ctx = SimpleNamespace(
        agent_id="scout",
        permissions={"allow_github_api": False},
        user_id=uuid4(),
    )
    result = await reg.execute("fetch_github_repo", {}, ctx)
    assert "error" in result
    assert result.get("code") == "AGENT_TOOL_DENIED"
    assert "allow_github_api" in result["error"]


@pytest.mark.asyncio
async def test_execute_allows_github_when_permission_true():
    reg = ToolRegistry()

    async def handler(**kwargs):
        return {"ok": True}

    reg.register(
        ToolDefinition(
            name="fetch_github_repo",
            description="t",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            allowed_agents=["scout"],
            required_permission="allow_github_api",
        )
    )
    ctx = SimpleNamespace(
        agent_id="scout",
        permissions={"allow_github_api": True},
        user_id=uuid4(),
    )
    result = await reg.execute("fetch_github_repo", {}, ctx)
    assert result == {"ok": True}
