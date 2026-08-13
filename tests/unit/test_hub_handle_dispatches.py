"""HubService._handle_dispatches 三分支测试(审查报告 §1.3 / §1.1)。

direct(单专家流式转 subagent 事件)、must_serial(串行)、并行(gather)
均用 monkeypatch _run_agent 返回固定 EngineResult,不碰真实 LLM。
"""

from agent_core.agents.hub import DispatchRoundOutcome, HubService
from agent_core.agents.react import EngineResult

from tests.sse_util import join_sse


class FakeRegistry:
    def __init__(self, known=None):
        self.known = known or {"hub", "scout", "mentor", "navigator", "curator", "scribe", "atlas"}

    def has(self, agent_id: str) -> bool:
        return agent_id in self.known

    def get(self, agent_id: str):
        return None


class FakeMemory:
    def __init__(self):
        self.short_memory_calls: list[dict] = []

    async def append_short_memory(self, agent_id, payload: dict):
        self.short_memory_calls.append({"agent_id": agent_id, **payload})


def make_service(monkeypatch, *, run_agent_result: EngineResult | None = None):
    service = HubService.__new__(HubService)
    from agent_core.agents.types import AgentEngineConfig
    service.config = AgentEngineConfig()
    service.registry = FakeRegistry()
    service.memory = FakeMemory()
    service.db = None
    run_calls: list[dict] = []

    async def fake_run_agent(self, **kwargs):
        run_calls.append(kwargs)
        if run_agent_result is not None:
            yield run_agent_result
        else:
            yield EngineResult(text=f"{kwargs['agent_id']}答复", agent_id=kwargs["agent_id"])

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)
    return service, run_calls


def run_dispatches(service, dispatches, *, finalize=False, bag=None):
    chunks = []
    async def iterate():
        async for c in service._handle_dispatches(
            dispatches=dispatches,
            session_id="s1",
            original_message="原始问题",
            llm=None,
            llm_config=None,
            raw_settings={},
            permissions={},
            project_id=None,
            history=[],
            hub_preamble="",
            finalize=finalize,
            result_bag=bag,
        ):
            chunks.append(c)
    import asyncio
    asyncio.run(iterate())
    return chunks


def test_direct_single_expert_streams_subagent(monkeypatch):
    service, run_calls = make_service(monkeypatch)
    bag = DispatchRoundOutcome()

    chunks = run_dispatches(
        service,
        [{"target_agent": "mentor", "task": "讲解", "reason": "学习"}],
        bag=bag,
    )

    joined = join_sse(chunks)
    assert "event: subagent_start" in joined
    assert '"agent_id": "mentor"' in joined
    assert "event: subagent_done" in joined
    assert '"status": "ok"' in joined
    assert len(run_calls) == 1
    assert run_calls[0]["agent_id"] == "mentor"
    assert run_calls[0]["message"] == "讲解"
    # 结果回填
    assert bag.expert_results == [("mentor", "mentor答复")]
    assert bag.nested_expert is True
    assert bag.direct_streamed is False
    assert bag.hub_passthrough is False


def test_direct_converts_thinking_text_to_subagent_channels(monkeypatch):
    service = HubService.__new__(HubService)
    from agent_core.agents.types import AgentEngineConfig
    service.config = AgentEngineConfig()
    service.registry = FakeRegistry()
    service.memory = FakeMemory()
    service.db = None
    run_calls: list[dict] = []

    async def fake_run_agent(self, **kwargs):
        run_calls.append(kwargs)
        # 专家引擎流式输出 thinking / text_delta → 应转成 subagent_thinking / subagent_text
        yield 'event: thinking\ndata: {"content": "专家思路"}\n\n'
        yield 'event: text_delta\ndata: {"content": "专家正文"}\n\n'
        yield 'event: tool_call\ndata: {"name": "web_search", "status": "running"}\n\n'
        yield EngineResult(text="", agent_id="mentor")

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)

    chunks = run_dispatches(service, [{"target_agent": "mentor", "task": "t", "reason": "r"}])

    joined = join_sse(chunks)
    assert 'event: subagent_thinking' in joined and "专家思路" in joined
    assert 'event: subagent_text' in joined and "专家正文" in joined
    # tool_call 走主通道透传
    assert "event: tool_call" in joined
    # 汇总后的 done 不重复透传
    assert "event: done" not in joined
    # 卡片输出取流式正文拼接(EngineResult 正文为空时)
    assert '"output": "专家正文"' in joined


def test_serial_dispatch_sequential(monkeypatch):
    service, run_calls = make_service(monkeypatch)
    bag = DispatchRoundOutcome()

    chunks = run_dispatches(
        service,
        [
            {"target_agent": "scout", "task": "速览", "reason": "r1"},
            {"target_agent": "mentor", "task": "讲解", "reason": "r2"},
        ],
        bag=bag,
    )

    # mentor 属串行集合 → 严格顺序执行
    assert [c["agent_id"] for c in run_calls] == ["scout", "mentor"]
    joined = join_sse(chunks)
    assert joined.count("event: subagent_start") == 2
    assert joined.count("event: subagent_done") == 2
    assert len(bag.expert_results) == 2
    assert len(bag.summaries) == 2


def test_parallel_dispatch_gather(monkeypatch):
    service, run_calls = make_service(monkeypatch)
    bag = DispatchRoundOutcome()

    chunks = run_dispatches(
        service,
        [
            {"target_agent": "scout", "task": "速览", "reason": "r1"},
            {"target_agent": "atlas", "task": "图谱", "reason": "r2"},
        ],
        bag=bag,
    )

    # scout + atlas 均非串行集合 → 并行 gather
    assert len(run_calls) == 2
    joined = join_sse(chunks)
    assert joined.count("event: subagent_start") == 2
    assert joined.count("event: subagent_done") == 2
    assert len(bag.expert_results) == 2


def test_direct_question_intercept(monkeypatch):
    service = HubService.__new__(HubService)
    from agent_core.agents.types import AgentEngineConfig
    service.config = AgentEngineConfig()
    service.registry = FakeRegistry()
    service.memory = FakeMemory()
    service.db = None

    async def fake_run_agent(self, **kwargs):
        yield EngineResult(text="", agent_id="mentor", question={"question_id": "q1"})

    monkeypatch.setattr(HubService, "_run_agent", fake_run_agent)
    bag = DispatchRoundOutcome()

    chunks = run_dispatches(
        service,
        [{"target_agent": "mentor", "task": "讲解", "reason": "学习"}],
        finalize=True,  # 即使要收口,反问也立即中断
        bag=bag,
    )

    joined = join_sse(chunks)
    assert 'event: subagent_done' in joined and '"status": "question"' in joined
    assert bag.had_question is True
    # 反问时落短期记忆并提前返回,不进入 merge finalize
    assert service.memory.short_memory_calls
    assert "pending_question" in service.memory.short_memory_calls[0]["summary"]
    # finalize=True 但反问拦截 → 没有汇总轮
    assert "[状态] Hub · 汇总中" not in joined


def test_unregistered_agent_skipped(monkeypatch):
    service, run_calls = make_service(monkeypatch)
    bag = DispatchRoundOutcome()

    chunks = run_dispatches(
        service,
        [{"target_agent": "unknown", "task": "t", "reason": "r"}],
        bag=bag,
    )

    joined = join_sse(chunks)
    assert "跳过未注册 Agent" in joined
    assert run_calls == []
    assert bag == DispatchRoundOutcome()
