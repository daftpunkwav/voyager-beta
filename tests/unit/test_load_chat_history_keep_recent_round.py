"""§4.4.1 load_chat_history 保留最近一轮 tool 交互的单测。"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agent_core.memory.context import ContextBuilder


def _make_msg(role: str, content: str):
    """构造一个 AgentMessage-like 的轻量对象。"""
    return SimpleNamespace(role=role, content=content)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


class _FakeMemory:
    """只实现 list_recent_messages 的假记忆服务。"""

    def __init__(self, msgs):
        self._msgs = msgs

    async def list_recent_messages(self, session_id, limit: int = 20):
        return self._msgs


class _FakeBuilder:
    """绕过完整构造(无需真实数据库)的 ContextBuilder 包装。"""

    def __init__(self, msgs):
        self._msgs = msgs

    async def load_chat_history(self, session_id, limit: int = 20):
        # 委托给真实的 ContextBuilder(用 mock 记忆)
        builder = ContextBuilder(db=None, memory=_FakeMemory(self._msgs))  # type: ignore[arg-type]
        return await builder.load_chat_history(session_id, limit=limit)


def test_load_chat_history_keeps_only_user_assistant_when_no_tool():
    """§4.4.1: 无 tool 消息时,全部保留 user/assistant。"""
    msgs = [
        _make_msg("user", "hello"),
        _make_msg("assistant", "hi"),
        _make_msg("user", "what is python?"),
        _make_msg("assistant", "a language"),
    ]
    builder = _FakeBuilder(msgs)
    result = asyncio.run(builder.load_chat_history(uuid4()))
    assert result == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "what is python?"},
        {"role": "assistant", "content": "a language"},
    ]


def test_load_chat_history_keeps_recent_assistant_tool_pair():
    """§4.4.1: 保留最近一轮的 assistant+tool 配对。"""
    msgs = [
        _make_msg("user", "first question"),
        _make_msg("assistant", "first answer"),
        _make_msg("user", "second question"),
        _make_msg("assistant", "calls tool X"),  # last_round_start = 3
        _make_msg("tool", "tool X result: 42"),  # 最近一轮,保留
    ]
    builder = _FakeBuilder(msgs)
    result = asyncio.run(builder.load_chat_history(uuid4()))
    assert len(result) == 5, f"expected 5 items, got {len(result)}"
    assert result[3] == {"role": "assistant", "content": "calls tool X"}
    assert result[4] == {"role": "tool", "content": "tool X result: 42"}


def test_load_chat_history_drops_older_tool_messages():
    """§4.4.1: 多轮历史中的旧 tool 消息,只保留最近一轮 tool。"""
    msgs = [
        _make_msg("assistant", "old assistant 1"),
        _make_msg("tool", "old tool 1"),  # 丢弃
        _make_msg("user", "user msg"),
        _make_msg("assistant", "middle"),
        _make_msg("tool", "old tool 2"),  # 丢弃
        _make_msg("user", "latest question"),
        _make_msg("assistant", "latest calls Y"),  # last_round_start = 6
        _make_msg("tool", "Y result"),  # 保留
    ]
    builder = _FakeBuilder(msgs)
    result = asyncio.run(builder.load_chat_history(uuid4()))
    # 保留全部 user/assistant + 最后一轮 tool
    roles = [m["role"] for m in result]
    assert roles == ["assistant", "user", "assistant", "user", "assistant", "tool"]
    # 保留的 tool 是 "Y result", 不是 "old tool 1" 或 "old tool 2"
    assert result[-1]["content"] == "Y result"


def test_load_chat_history_keeps_only_assistant_when_no_tool_following():
    """§4.4.1: 仅有 assistant 且后面没 tool 时,只保留 assistant。"""
    msgs = [
        _make_msg("user", "q"),
        _make_msg("assistant", "no tool called"),
    ]
    builder = _FakeBuilder(msgs)
    result = asyncio.run(builder.load_chat_history(uuid4()))
    assert result == [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "no tool called"},
    ]


def test_load_chat_history_drops_tool_at_start_keeps_user_assistant():
    """§4.4.1: 开头有 tool 但最后没 tool 时,丢弃旧 tool。"""
    msgs = [
        _make_msg("user", "u1"),
        _make_msg("assistant", "a1"),
        _make_msg("tool", "old tool"),  # 丢弃
        _make_msg("user", "u2"),
        _make_msg("assistant", "a2"),  # 最后,后面没 tool
    ]
    builder = _FakeBuilder(msgs)
    result = asyncio.run(builder.load_chat_history(uuid4()))
    assert result == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]


def test_load_chat_history_includes_system_messages():
    """§4.4.1: system 消息正常保留(无条件保留)。"""
    msgs = [
        _make_msg("system", "you are helpful"),
        _make_msg("user", "q"),
        _make_msg("assistant", "a"),
    ]
    builder = _FakeBuilder(msgs)
    result = asyncio.run(builder.load_chat_history(uuid4()))
    assert len(result) == 3
    assert result[0]["role"] == "system"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
