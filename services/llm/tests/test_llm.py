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

    async def test_agent_cannot_set_loopback_base_url(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "add_provider", AGENT_CTX, {
                "display_name": "劫持", "base_url": "http://127.0.0.1:9/v1",
                "api_format": "chat", "models": ["m"],
            })
        assert exc.value.body.code == "LLM.FORBIDDEN"

    async def test_user_may_set_loopback_base_url(self, deps) -> None:
        out = await execute(registry, "add_provider", USER_CTX, {
            "display_name": "本地", "base_url": "http://127.0.0.1:11434/v1",
            "api_format": "chat", "models": ["llama"],
        })
        assert "11434" in out["base_url"]

    async def test_agent_cannot_change_base_url_via_update(self, deps) -> None:
        """phase-13:改 base_url 会把已存 key 打到新主机,update 仅用户可改。"""
        pid = await _add_sample()
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "update_provider", AGENT_CTX, {
                "provider_id": pid, "base_url": "https://evil.example/v1",
            })
        assert exc.value.body.code == "LLM.FORBIDDEN"
        store, _ = deps
        assert store.get(pid)["base_url"] == "https://api.test/v1"  # 未被 upsert

    async def test_agent_may_update_metadata_without_base_url(self, deps) -> None:
        """只改名称/模型清单等元数据:本阶段保持 agent 可调(parity)。"""
        pid = await _add_sample()
        out = await execute(registry, "update_provider", AGENT_CTX, {
            "provider_id": pid, "display_name": "新名字", "models": ["m9"],
        })
        assert out["display_name"] == "新名字"
        assert out["base_url"] == "https://api.test/v1"

    async def test_user_changes_base_url_ok(self, deps) -> None:
        pid = await _add_sample()
        out = await execute(registry, "update_provider", USER_CTX, {
            "provider_id": pid, "base_url": "https://api.new/v2",
        })
        assert out["base_url"] == "https://api.new/v2"

    async def test_key_without_material_reads_back_guide(self, deps, monkeypatch) -> None:
        """本机未配密钥材料:统一错误体带引导文案,而非 500。"""
        from platform_secrets import SecretUnavailableError

        def boom(key: str, plain: str) -> None:
            raise SecretUnavailableError("未配置密钥材料")

        monkeypatch.setattr(deps[1], "set", boom)
        pid = await _add_sample()
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "set_api_key", USER_CTX,
                          {"provider_id": pid, "api_key": "sk-x"})
        assert exc.value.body.code == "LLM.UNAVAILABLE"
        assert "SECRETS_ENCRYPTION_KEY" in exc.value.body.hint


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


class TestMessageTranslation:
    """中性历史 → 各家请求体的消息翻译:成对历史走原生 tool 协议 + 孤儿降级 + 错误带响应体。

    Phase 04 起 agent REACT 成对回填 assistant.tool_calls 与带 id 的 tool 结果
    (见 agent/subagent/modes.py _react),翻译层把成对历史编成 OpenAI
    tool_call_id / Anthropic tool_use_id 原生形状。历史里仍可能残留孤儿
    (Phase 01–03 旧会话、compressor 剪枝删掉 assistant、中断残环),孤儿原样
    发出会被 Anthropic 系端点(如 MiniMax 兼容层,错误 2013 "tool result's
    tool id not found")与严格 OpenAI 端点 400,且一旦进历史,该会话后续每轮
    请求都被拒,故仍降级为 user 文本兜底。
    """

    _real_client: ClassVar[type] = httpx.AsyncClient

    def _patch(self, monkeypatch, handler) -> None:
        real = self._real_client
        monkeypatch.setattr(
            client_mod.httpx, "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )

    _ANTHROPIC = {"id": "p", "base_url": "https://api.test/anthropic",
                  "api_format": "anthropic"}
    _CHAT = {"id": "p", "base_url": "https://api.test/v1", "api_format": "chat"}
    _HISTORY = [
        {"role": "system", "content": "你是助手。"},
        {"role": "user", "content": "帮我添加供应商"},
        {"role": "tool", "name": "ask_user", "content": "[工具结果] 用户未响应"},
    ]
    # 成对历史(模拟 _react 回填):assistant 带 tool_calls,结果带同一 id
    _PAIRED = [
        {"role": "system", "content": "你是助手。"},
        {"role": "user", "content": "调用工具"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "name": "echo_tool", "arguments": {"x": "a"}},
            {"id": "call_2", "name": "echo_tool", "arguments": {"x": "b"}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "name": "echo_tool", "content": "echo:a"},
        {"role": "tool", "tool_call_id": "call_2", "name": "echo_tool", "content": "echo:b"},
        {"role": "user", "content": "继续"},
    ]

    async def test_anthropic_flattens_bare_tool_role(self, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        out = await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m",
                                        messages=self._HISTORY)
        assert out.text == "ok"
        roles = [m["role"] for m in seen["body"]["messages"]]
        assert "tool" not in roles  # 端点不接受 role:"tool"
        last = seen["body"]["messages"][-1]
        assert last["role"] == "user"
        assert "ask_user" in last["content"] and "用户未响应" in last["content"]

    async def test_chat_format_flattens_bare_tool_role(self, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m",
                                  messages=self._HISTORY)
        roles = [m["role"] for m in seen["body"]["messages"]]
        assert "tool" not in roles

    async def test_chat_paired_tool_calls_native_shape(self, monkeypatch) -> None:
        """成对历史在 chat 格式走 OpenAI 原生 tool 协议,不再 flatten。"""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m",
                                  messages=self._PAIRED)
        msgs = seen["body"]["messages"]
        # 成对消息保留原生 role,不降级
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "tool", "user"]
        # assistant.tool_calls 补成 OpenAI 形状:type:function + arguments JSON 字符串
        assert msgs[2]["tool_calls"] == [
            {"id": "call_1", "type": "function",
             "function": {"name": "echo_tool", "arguments": '{"x": "a"}'}},
            {"id": "call_2", "type": "function",
             "function": {"name": "echo_tool", "arguments": '{"x": "b"}'}},
        ]
        # tool 结果带 tool_call_id,与 assistant 配对
        assert [m["tool_call_id"] for m in msgs[3:5]] == ["call_1", "call_2"]

    async def test_anthropic_paired_tool_use_blocks(self, monkeypatch) -> None:
        """成对历史在 anthropic 格式发 tool_use / tool_result 内容块,不再压成纯字符串。"""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m",
                                  messages=self._PAIRED)
        msgs = seen["body"]["messages"]
        # system 已抽出;assistant 用内容块,空 content 不产生空 text 块
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "user"]
        assert msgs[1]["content"] == [
            {"type": "tool_use", "id": "call_1", "name": "echo_tool", "input": {"x": "a"}},
            {"type": "tool_use", "id": "call_2", "name": "echo_tool", "input": {"x": "b"}},
        ]
        # 同一 assistant 回合的多个结果合并进一条 user,tool_use_id 与 tool_use 同 id
        assert msgs[2]["content"] == [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "echo:a"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "echo:b"},
        ]

    async def test_orphan_tool_flattens_alongside_paired(self, monkeypatch) -> None:
        """成对与孤儿同历史:成对走原生形状,孤儿(旧环/剪枝残留)仍降级为 user 文本。"""
        seen = {}
        history = [*self._PAIRED, {"role": "tool", "name": "legacy", "content": "旧残留"}]

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m",
                                  messages=history)
        msgs = seen["body"]["messages"]
        assert any(
            m["role"] == "assistant" and isinstance(m["content"], list)
            and any(b.get("type") == "tool_use" for b in m["content"])
            for m in msgs
        )
        last = msgs[-1]
        assert last["role"] == "user" and isinstance(last["content"], str)
        assert "legacy" in last["content"] and "旧残留" in last["content"]

    async def test_incomplete_pair_strips_unmatched_tool_calls(self, monkeypatch) -> None:
        """assistant 声明了 a/b 但只有 a 的结果:发出去的副本只留 a,避免端点 400。"""
        seen = {}
        history = [
            {"role": "user", "content": "调用工具"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "name": "echo_tool", "arguments": {"x": "a"}},
                {"id": "call_2", "name": "echo_tool", "arguments": {"x": "b"}},
            ]},
            {"role": "tool", "tool_call_id": "call_1", "name": "echo_tool", "content": "echo:a"},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m", messages=history)
        msgs = seen["body"]["messages"]
        assistant = next(m for m in msgs if m["role"] == "assistant")
        assert [tc["id"] for tc in assistant["tool_calls"]] == ["call_1"]
        tools = [m for m in msgs if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tools] == ["call_1"]

    async def test_chat_empty_messages_never_sends_empty_array(self, monkeypatch) -> None:
        """chat 分支空历史同样不发空 messages 数组。"""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m", messages=[])
        assert seen["body"]["messages"]

    async def test_anthropic_rest_empty_never_sends_empty_messages(self, monkeypatch) -> None:
        """只有 system 的历史:不发空 messages 数组(MiniMax 2013 的空 messages)。"""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1}, "model": "m",
            })

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m",
                                  messages=[{"role": "system", "content": "只有系统提示"}])
        assert seen["body"]["messages"]
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={
                "type": "error",
                "error": {"type": "invalid_request_error",
                          "message": "invalid params, tool result's tool id() not found (2013)"},
            })

        self._patch(monkeypatch, handler)
        with pytest.raises(httpx.HTTPStatusError) as exc:
            await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m",
                                      messages=[{"role": "user", "content": "hi"}])
        assert "2013" in str(exc.value)  # 供应商真实错误原因进入异常信息(用户气泡可见)
