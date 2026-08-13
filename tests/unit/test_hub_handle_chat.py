"""HubService.handle_chat / handle_question_answer 主链路测试(审查报告 §1.3)。

用假 registry/memory/context_builder + monkeypatch 配置加载与 _run_agent,
不碰真实 LLM 与数据库。
"""

from agent_core.agents.hub import HubService
from agent_core.agents.react import EngineResult
from agent_core.agents.stream_events import format_sse
from agent_core.llm.provider import LLMProvider


class FakeRegistry:
    def __init__(self, known: set[str] | None = None):
        self.known = known or {"hub", "scout", "mentor", "navigator", "curator", "scribe", "atlas"}

    def has(self, agent_id: str) -> bool:
        return agent_id in self.known

    def get(self, agent_id: str):
        return None  # handle_chat 主链路不消费 get()


class FakeMemory:
    def __init__(self):
        self.short_memory_calls: list[dict] = []
        self.propose_calls: list[dict] = []

    async def append_short_memory(self, agent_id, payload: dict):
        self.short_memory_calls.append({"agent_id": agent_id, **payload})

    async def propose_memory(self, *, agent_id, value, confidence, evidence=None, kind="long_memory", apply=False):
        self.propose_calls.append(
            {"agent_id": agent_id, "value": value, "confidence": confidence,
             "evidence": evidence, "kind": kind, "apply": apply}
        )
        return {"status": "applied"}


class FakeContextBuilder:
    def __init__(self):
        self.history = []

    async def load_chat_history(self, session_id, limit: int = 20) -> list:
        return list(self.history)


def make_service(monkeypatch, *, registry=None, memory=None):
    """构造绕过 __init__ 的 HubService 并打桩外部依赖。"""
    service = HubService.__new__(HubService)
    service.registry = registry or FakeRegistry()
    service.memory = memory or FakeMemory()
    service.context_builder = FakeContextBuilder()
    service.db = None
    service.engine = None
    # 无 LLM 配置 → LLMProvider(None).available=False → 意图走纯规则
    async def _no_bundle(self):
        return (LLMProvider(None), None, "ok", {}, {})

    monkeypatch.setattr(HubService, "_load_user_bundle", _no_bundle)
    return service


def fake_user(**overrides):
    attrs = dict(
        id="u1",
        settings_json="{}",
        agent_permissions="{}",
    )
    attrs.update(overrides)
    return type("U", (), attrs)()


def test_handle_chat_normal_hub_flow(monkeypatch):
    service = make_service(monkeypatch)
    memory = service.memory
    run_calls: list[dict] = []

    async def fake_run_agent(self, **kwargs):
        run_calls.append(kwargs)
        yield format_sse(
            "done",
            {"usage": {"tokens": 0}, "iterations": 1, "agent_id": kwargs["agent_id"]},
        )
        yield EngineResult(text="完成", agent_id=kwargs["agent_id"])

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    chunks = []
    async def iterate():
        async for c in service.handle_chat(
            session_id="s1", message="帮我分析一下 Voyager"
        ):
            chunks.append(c)
    import asyncio
    asyncio.run(iterate())

    # 事件序列:thinking(意图)→ done
    assert chunks and "event: thinking" in chunks[0]
    assert any("event: done" in c for c in chunks)
    # 规则命中 scout(confidence 0.9 ≥ 0.85)→ 快速编排前缀
    assert run_calls and run_calls[0]["agent_id"] == "hub"
    assert "[快速编排]" in run_calls[0]["message"]
    assert run_calls[0]["chitchat_mode"] is False
    # 落短期记忆
    assert len(memory.short_memory_calls) == 1
    assert "完成" in memory.short_memory_calls[0]["summary"]


def test_handle_chat_force_agent_direct(monkeypatch):
    service = make_service(monkeypatch)
    run_calls: list[dict] = []

    async def fake_run_agent(self, **kwargs):
        run_calls.append(kwargs)
        yield format_sse("done", {"usage": {"tokens": 0}, "iterations": 1, "agent_id": kwargs["agent_id"]})
        yield EngineResult(text="讲解", agent_id=kwargs["agent_id"])

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    chunks = []
    async def iterate():
        async for c in service.handle_chat( session_id="s1", message="讲讲 FastAPI", force_agent="mentor"
        ):
            chunks.append(c)
    import asyncio
    asyncio.run(iterate())

    assert any("event: agent_switch" in c and '"to": "mentor"' in c for c in chunks)
    assert run_calls and run_calls[0]["agent_id"] == "mentor"
    # 直达消息不加编排前缀
    assert run_calls[0]["message"] == "讲讲 FastAPI"


def test_handle_chat_chitchat_fast_path(monkeypatch):
    service = make_service(monkeypatch)
    run_calls: list[dict] = []

    async def fake_run_agent(self, **kwargs):
        run_calls.append(kwargs)
        yield format_sse("done", {"usage": {"tokens": 0}, "iterations": 1, "agent_id": "hub"})
        yield EngineResult(text="你好", agent_id="hub")

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    chunks = []
    async def iterate():
        async for c in service.handle_chat(session_id="s1", message="你好"):
            chunks.append(c)
    import asyncio
    asyncio.run(iterate())

    assert run_calls and run_calls[0]["chitchat_mode"] is True
    # 寒暄不进快速编排/编排提示前缀
    assert "[快速编排]" not in run_calls[0]["message"]
    assert "[编排提示]" not in run_calls[0]["message"]


def test_handle_chat_multi_goes_orchestrate(monkeypatch):
    service = make_service(monkeypatch)
    orch_calls: list[dict] = []
    run_calls: list[dict] = []

    async def fake_orchestrate_multi(self, **kwargs):
        orch_calls.append(kwargs)
        yield format_sse("done", {"usage": {"tokens": 0}, "iterations": 1, "agent_id": "hub"})

    async def fake_run_agent(self, **kwargs):
        run_calls.append(kwargs)

    monkeypatch.setattr(HubService, "_orchestrate_multi", fake_orchestrate_multi)
    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    chunks = []
    async def iterate():
        async for c in service.handle_chat( session_id="s1", message="分析一下 X 并且整理笔记"
        ):
            chunks.append(c)
    import asyncio
    asyncio.run(iterate())

    # scout(分析) + scribe(笔记) → multi → 走 _orchestrate_multi,不再调 _run_agent
    assert orch_calls and orch_calls[0]["intent"].is_multi
    assert run_calls == []


def test_handle_chat_question_early_return(monkeypatch):
    service = make_service(monkeypatch)
    memory = service.memory

    async def fake_run_agent(self, **kwargs):
        yield EngineResult(text="", agent_id="hub", question={"question_id": "q1"})

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    chunks = []
    async def iterate():
        async for c in service.handle_chat(session_id="s1", message="你好呀帮我分析"):
            chunks.append(c)
    import asyncio
    asyncio.run(iterate())

    # 反问挂起即结束,不再落短期记忆
    assert len(chunks) == 1  # 只有意图 thinking
    assert memory.short_memory_calls == []


def test_handle_question_answer_writes_extracted_prefs(monkeypatch):
    """反问回答:画像写入提取后的结构化值,而非原始 answers dump(§2.3)。"""
    service = make_service(monkeypatch)
    memory = service.memory
    run_calls: list[dict] = []

    async def fake_run_agent(self, **kwargs):
        run_calls.append(kwargs)
        yield format_sse("done", {"usage": {"tokens": 0}, "iterations": 1, "agent_id": "hub"})
        yield EngineResult(text="继续答复", agent_id="hub")

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    answers = {
        "q1": {"type": "radio", "value": "精通", "question_id": "q1"},
    }
    chunks = []
    async def iterate():
        async for c in service.handle_question_answer( session_id="s1", question_id="q1", answers=answers
        ):
            chunks.append(c)
    import asyncio
    asyncio.run(iterate())

    assert any("event: agent_switch" in c for c in chunks)
    assert run_calls and "用户反问回答" in run_calls[0]["message"]
    # 画像写入:提取 value 而非嵌套 dump
    assert len(memory.propose_calls) == 1
    import json
    value = json.loads(memory.propose_calls[0]["value"])
    assert value == {"q1": "精通"}
    assert memory.propose_calls[0]["kind"] == "preference"
    assert memory.propose_calls[0]["apply"] is True


def test_handle_question_answer_skipped_no_prefs(monkeypatch):
    service = make_service(monkeypatch)
    memory = service.memory

    async def fake_run_agent(self, **kwargs):
        yield EngineResult(text="好的", agent_id="hub")

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    async def iterate():
        async for _ in service.handle_question_answer( session_id="s1", question_id="q1",
            answers={}, skipped=True,
        ):
            pass
    import asyncio
    asyncio.run(iterate())

    assert memory.propose_calls == []
