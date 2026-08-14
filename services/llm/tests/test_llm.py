"""llm 服务测试:提供商目录、secret 边界、连接测试、用量统计。

网络出口一律 mock(httpx.MockTransport),测试不触网。
"""

import json
from typing import ClassVar

import httpx
import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_secrets import SecretStore

from services.llm import client as client_mod
from services.llm.capabilities import Deps, init_deps, registry
from services.llm.store import ProviderStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def deps(tmp_path, monkeypatch):
    store = ProviderStore(tmp_path / "llm.db")
    secrets = SecretStore(tmp_path / "secrets.db", key_material="test")
    init_deps(Deps(store=store, secrets=secrets))
    # 网络出口统一替换为 MockTransport(真实 chat 格式应答)
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "pong"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                "model": "gpt-4o-mini",
            })
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "pong"}],
            "usage": {"input_tokens": 3, "output_tokens": 1}, "model": "claude",
        })

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        client_mod.httpx, "AsyncClient",
        lambda **kw: orig(transport=httpx.MockTransport(mock_handler), **kw),
    )
    yield store, secrets
    store.close()
    secrets.close()


async def _add_sample() -> str:
    out = await execute(registry, "add_provider", USER_CTX, {
        "display_name": "测试商", "base_url": "https://api.test/v1",
        "api_format": "chat", "models": ["m1", "m2"],
    })
    return out["id"]


class TestCatalog:
    async def test_builtin_catalog(self, deps) -> None:
        out = await execute(registry, "list_builtin_providers", AGENT_CTX, {})
        assert any(p["preset_id"] == "openai" for p in out)
        defaults = await execute(
            registry, "get_provider_defaults", AGENT_CTX, {"preset_id": "moonshot"}
        )
        assert defaults["api_format"] == "chat"

    async def test_bad_format_rejected(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "add_provider", USER_CTX, {
                "display_name": "x", "base_url": "https://x", "api_format": "magic",
            })
        assert exc.value.body.code == "LLM.INVALID_INPUT"


class TestSecretBoundary:
    async def test_agent_cannot_write_api_key(self, deps) -> None:
        pid = await _add_sample()
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "set_api_key", AGENT_CTX,
                          {"provider_id": pid, "api_key": "sk-x"})
        assert exc.value.body.code == "LLM.FORBIDDEN"  # 场景 G 的隐私例外

    async def test_user_writes_key_listing_shows_flag_only(self, deps) -> None:
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX,
                      {"provider_id": pid, "api_key": "sk-secret"})
        providers = await execute(registry, "list_providers", AGENT_CTX, {})
        mine = next(p for p in providers if p["id"] == pid)
        assert mine["has_api_key"] is True
        assert "sk-secret" not in repr(providers)  # key 永不出现在能力出口


class TestConnectionAndUsage:
    async def test_test_connection_ok(self, deps) -> None:
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX,
                      {"provider_id": pid, "api_key": "sk-x"})
        out = await execute(registry, "test_connection", USER_CTX,
                            {"provider_id": pid, "model": "m1"})
        assert out["ok"] is True and out["latency_ms"] >= 0

    async def test_test_connection_without_key(self, deps) -> None:
        pid = await _add_sample()
        with pytest.raises(ServiceError, match="api key"):
            await execute(registry, "test_connection", USER_CTX, {"provider_id": pid})

    async def test_complete_records_usage(self, deps) -> None:
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX,
                      {"provider_id": pid, "api_key": "sk-x"})
        out = await execute(registry, "complete", AGENT_CTX, {
            "provider_id": pid, "model": "m1",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert out["text"] == "pong"
        stats = await execute(registry, "get_usage_stats", USER_CTX, {"days": 1})
        assert stats["calls"] == 1 and stats["input_tokens"] == 3
        assert stats["by_model"][0]["model"] == "gpt-4o-mini"


class TestCompleteWithTools:
    """tools 双格式:入参统一中性格式,请求体按 api_format 转换,tool_calls 统一解析。"""

    TOOLS: ClassVar[list[dict]] = [{
        "name": "create_note",
        "description": "建笔记",
        "schema": {"type": "object", "properties": {"title": {"type": "string"}}},
    }]
    # 类定义时绑定真实构造器:deps fixture 已 patch httpx.AsyncClient,二次覆盖需绕开
    _real_client: ClassVar[type] = httpx.AsyncClient

    def _patch(self, monkeypatch, handler) -> None:
        real = self._real_client
        monkeypatch.setattr(
            client_mod.httpx, "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )

    async def _add(self, api_format: str) -> str:
        out = await execute(registry, "add_provider", USER_CTX, {
            "display_name": "测试商", "base_url": "https://api.test/v1",
            "api_format": api_format, "models": ["m1"],
        })
        await execute(registry, "set_api_key", USER_CTX,
                      {"provider_id": out["id"], "api_key": "sk-x"})
        return out["id"]

    async def test_chat_format(self, deps, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["tools"] = json.loads(request.content).get("tools")
            return httpx.Response(200, json={
                "choices": [{"message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "create_note",
                                     "arguments": '{"title": "t"}'},
                    }],
                }}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                "model": "gpt-4o-mini",
            })

        self._patch(monkeypatch, handler)
        pid = await self._add("chat")
        out = await execute(registry, "complete", AGENT_CTX, {
            "provider_id": pid, "model": "m1",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": self.TOOLS,
        })
        # 请求体转换为 OpenAI function 格式
        assert seen["tools"] == [{"type": "function", "function": {
            "name": "create_note", "description": "建笔记",
            "parameters": self.TOOLS[0]["schema"],
        }}]
        # 应答的 JSON 字符串 arguments 解析为 dict
        assert out["tool_calls"] == [{"id": "call_1", "name": "create_note",
                                      "arguments": {"title": "t"}}]

    async def test_anthropic_format(self, deps, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["tools"] = json.loads(request.content).get("tools")
            return httpx.Response(200, json={
                "content": [
                    {"type": "text", "text": "调用工具"},
                    {"type": "tool_use", "id": "tu_1", "name": "create_note",
                     "input": {"title": "t"}},
                ],
                "usage": {"input_tokens": 5, "output_tokens": 2},
                "model": "claude",
            })

        self._patch(monkeypatch, handler)
        pid = await self._add("anthropic")
        out = await execute(registry, "complete", AGENT_CTX, {
            "provider_id": pid, "model": "m1",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": self.TOOLS,
        })
        assert seen["tools"] == [{
            "name": "create_note", "description": "建笔记",
            "input_schema": self.TOOLS[0]["schema"],
        }]
        assert out["text"] == "调用工具"
        assert out["tool_calls"] == [{"id": "tu_1", "name": "create_note",
                                      "arguments": {"title": "t"}}]

    async def test_without_tools_no_field_in_body(self, deps, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "pong"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "m1",
            })

        self._patch(monkeypatch, handler)
        pid = await self._add("chat")
        out = await execute(registry, "complete", AGENT_CTX, {
            "provider_id": pid, "messages": [{"role": "user", "content": "hi"}],
        })
        assert "tools" not in seen["body"]  # 不传 tools 时请求体不带该字段
        assert out["tool_calls"] == []
