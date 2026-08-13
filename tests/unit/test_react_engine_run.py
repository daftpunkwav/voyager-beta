"""ReActEngine.run 主链路测试 —— 用脚本化 FakeLLM + FakeToolRegistry,不碰真实网络。

覆盖(审查报告 §1.3):
- 单轮无工具(流式快路径)
- 多轮工具环(先 tool_call 后正文)
- 达到 max_iter 上限
- LLM 抛异常
- 降级(llm.available=False)
- plan_nudge 纠正(纯计划宣告 → 追加纠正消息 → 第二轮正常)
- 反问拦截(__question__ → EngineResult.question)
- Hub 调度拦截(__dispatch__ → EngineResult.dispatches)
- CoT 两阶段(thinking/text_delta 通道分流、usage 累加、phase1 失败中止)
"""

from agent_core.agents.react import EngineResult, ReActEngine
from agent_core.agents.registry import AgentDefinition
from agent_core.llm.provider import LLMChunk, LLMCompleteResult
from agent_core.memory.context import AgentRunContext

from tests.sse_util import join_sse


def _agent(**overrides) -> AgentDefinition:
    base = dict(
        id="scout",
        name="Scout",
        description="测试 Agent",
        tools=[],
        capabilities=["tools", "streaming"],
        system_prompt="你是测试 Agent。",
        soul={"persona": "test"},
        workflow="react",
        max_tokens=2048,
        max_iterations=6,
    )
    base.update(overrides)
    return AgentDefinition(**base)


class FakeLLM:
    """鸭子类型 LLMProvider:complete(stream=False) 按队列出牌,stream=True 出 chunk 流。"""

    def __init__(
        self,
        results: list[LLMCompleteResult] | None = None,
        stream_scripts: list[list[LLMChunk]] | None = None,
        *,
        available: bool = True,
        error: Exception | None = None,
    ):
        self.results = list(results or [])
        self.stream_scripts = [list(s) for s in (stream_scripts or [])]
        self.available = available
        self.error = error
        self.calls: list[dict] = []

    async def complete(
        self,
        messages,
        tools=None,
        temperature=0.7,
        max_tokens=4096,
        stream=False,
        model_override=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "stream": stream,
                "max_tokens": max_tokens,
            }
        )
        if self.error:
            raise self.error
        if stream:
            chunks = self.stream_scripts.pop(0) if self.stream_scripts else []

            async def gen():
                for c in chunks:
                    yield c

            return gen()
        if not self.results:
            return LLMCompleteResult(text="")
        return self.results.pop(0)


class FakeToolRegistry:
    def __init__(self, schemas: list[dict] | None = None, results: dict | None = None):
        self.schemas = schemas or []
        self.results = results or {}
        self.executed: list[tuple[str, dict]] = []

    def openai_tools_for(self, agent_id: str) -> list[dict]:
        return [dict(s) for s in self.schemas]

    async def execute(self, name: str, args: dict, ctx) -> dict:
        self.executed.append((name, args))
        return dict(self.results.get(name, {"ok": True}))


def _ctx(engine: ReActEngine, agent_def: AgentDefinition, fake_llm: FakeLLM) -> AgentRunContext:
    return AgentRunContext(
        session_id="s1",
        agent_id=agent_def.id,
        db=None,
        llm=fake_llm,
        llm_config=None,
        memory=None,
        tool_registry=FakeToolRegistry(
            schemas=[
                {"function": {"name": n}} for n in agent_def.tools
            ]
        ),
        extra={},
    )


def _collect(engine, agent_def, fake_llm, messages=None, ctx=None):
    ctx = ctx or _ctx(engine, agent_def, fake_llm)
    chunks = []
    result = None
    async def iterate():
        nonlocal result
        async for item in engine.run(
            agent_def=agent_def, ctx=ctx, messages=messages or [{"role": "user", "content": "hi"}]
        ):
            if isinstance(item, EngineResult):
                result = item
            else:
                chunks.append(item)
    import asyncio
    asyncio.run(iterate())
    return chunks, result, ctx


# —— 单轮无工具:流式快路径 ——

def test_run_single_round_no_tools_streams():
    agent_def = _agent()  # react + 无工具 → _prefer_token_stream
    fake = FakeLLM(
        stream_scripts=[
            [
                LLMChunk(type="text", text="你"),
                LLMChunk(type="text", text="好"),
                LLMChunk(type="done", usage={"total_tokens": 5}),
            ]
        ]
    )
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake)

    joined = join_sse(chunks)
    assert "event: thinking" in joined  # 生成中状态
    assert 'event: text_delta' in joined
    assert '"content": "你"' in joined and '"content": "好"' in joined
    assert 'event: done' in joined
    assert result is not None
    assert result.text == "你好"
    assert result.iterations == 1
    assert result.usage.get("total_tokens") == 5


# —— 多轮工具环:先 tool_call 后正文 ——

def test_run_tool_loop_multi_round():
    agent_def = _agent(tools=["web_search"])
    fake = FakeLLM(
        results=[
            LLMCompleteResult(
                text="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "function": {"name": "web_search", "arguments": '{"q": "python"}'},
                    }
                ],
            ),
            LLMCompleteResult(text="最终答复正文", tool_calls=[]),
        ]
    )
    engine = ReActEngine()
    chunks, result, ctx = _collect(engine, agent_def, fake)

    assert ctx.tool_registry.executed == [("web_search", {"q": "python"})]
    joined = join_sse(chunks)
    assert 'event: tool_call' in joined
    assert 'event: tool_result' in joined
    assert 'event: text_delta' in joined
    assert result is not None
    assert result.text == "最终答复正文"
    assert result.iterations == 2
    # 工具轮进消息历史
    tool_msgs = [m for m in fake.calls[1]["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 1


# —— 达到 max_iter:工具轮耗尽后走收口补写 ——

def test_run_tool_loop_max_iter_then_closing():
    agent_def = _agent(tools=["web_search"])
    tc = {
        "id": "call_x",
        "function": {"name": "web_search", "arguments": '{"q": "x"}'},
    }
    fake = FakeLLM(
        results=[LLMCompleteResult(text="", tool_calls=[tc]) for _ in range(10)],
        stream_scripts=[
            [
                LLMChunk(type="text", text="收口补写正文"),
                LLMChunk(type="done", usage={"total_tokens": 3}),
            ]
        ],
    )
    engine = ReActEngine(max_iterations=2)
    chunks, result, _ = _collect(engine, agent_def, fake)

    assert result is not None
    assert result.iterations == 2  # 达到上限,不再追加
    assert result.text == "收口补写正文"
    joined = join_sse(chunks)
    assert "[收口]" in joined
    # 工具只执行了 max_iter 轮
    assert len(fake.calls) == 3  # 2 轮工具 + 1 轮收口流式


# —— LLM 抛异常 ——

def test_run_llm_error_yields_error_sse():
    agent_def = _agent(tools=["web_search"])
    fake = FakeLLM(error=RuntimeError("boom"))
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake)

    assert any("LLM_ERROR" in c for c in chunks)
    assert result is not None
    assert "LLM 调用失败" in result.text
    assert result.iterations == 1


# —— 降级:llm.available=False ——

def test_run_degraded_no_llm():
    agent_def = _agent()
    fake = FakeLLM(available=False)
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake)

    assert result is not None
    assert result.iterations == 0
    assert result.text
    assert any('"degraded": true' in c for c in chunks)
    # 降级固定文案以 text_delta 切片发出
    assert any("event: text_delta" in c for c in chunks)


# —— plan_nudge:纯计划宣告 → 纠正后正常输出 ——

def test_run_plan_nudge_corrects_announcement():
    agent_def = _agent(id="hub", workflow="plan_execute", tools=["dispatch_agent"])
    fake = FakeLLM(
        stream_scripts=[
            # 规划阶段(stream=True)
            [LLMChunk(type="text", text="1. 调度 mentor\n2. 汇总"), LLMChunk(type="done")],
        ],
        results=[
            # 第一轮:只宣布计划,不调工具 → 命中 is_plan_announcement
            LLMCompleteResult(text="执行计划：\n1. 调度 mentor 讲解\n2. 汇总给用户", tool_calls=[]),
            # 第二轮:正常交付
            LLMCompleteResult(text="这是最终完整答复", tool_calls=[]),
        ],
    )
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake)

    joined = join_sse(chunks)
    assert "[纠正]" in joined  # 追加了纠正提示
    assert result is not None
    assert result.text == "这是最终完整答复"
    assert result.iterations == 2
    # 纠正消息确实进入了第二轮 LLM 调用
    second_msgs = fake.calls[1]["messages"]
    assert any(
        isinstance(m.get("content"), str) and "空承诺" in m.get("content")
        for m in second_msgs
    )


# —— 反问拦截 ——

def test_run_question_intercept():
    agent_def = _agent(tools=["ask_user"])
    question_result = {
        "__question__": True,
        "title": "确认一下",
        "items": [
            {
                "type": "single_choice",
                "id": "q1",
                "prompt": "你的水平?",
                "options": [
                    {"value": "a", "label": "初学"},
                    {"value": "b", "label": "精通"},
                ],
            }
        ],
    }
    fake = FakeLLM(
        results=[
            LLMCompleteResult(
                text="",
                tool_calls=[
                    {
                        "id": "call_q",
                        "function": {"name": "ask_user", "arguments": "{}"},
                    }
                ],
            ),
        ]
    )
    ctx = AgentRunContext(
        session_id="s1",
        agent_id=agent_def.id,
        db=None,
        llm=fake,
        llm_config=None,
        memory=None,
        tool_registry=FakeToolRegistry(
            schemas=[{"function": {"name": "ask_user"}}],
            results={"ask_user": question_result},
        ),
        extra={},
    )
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake, ctx=ctx)

    assert result is not None
    assert result.question is not None
    qs = result.question.get("questions") or []
    assert qs and qs[0].get("id") == "q1"  # 题干 id 保留
    assert result.question.get("question_id")  # 面板 id 由引擎生成
    assert result.pending_status == "pending_question"
    assert ctx.extra.get("pending_question") is not None
    assert any("event: question" in c for c in chunks)
    assert any('"pending_question": true' in c for c in chunks)


# —— Hub 调度拦截 ——

def test_run_dispatch_intercept():
    agent_def = _agent(id="hub", workflow="plan_execute", tools=["dispatch_agent"])
    dispatch = {
        "__dispatch__": True,
        "target_agent": "mentor",
        "task": "讲解 CrewAI",
        "reason": "学习任务",
    }
    fake = FakeLLM(
        results=[
            LLMCompleteResult(
                text="",
                tool_calls=[
                    {
                        "id": "call_d",
                        "function": {"name": "dispatch_agent", "arguments": "{}"},
                    }
                ],
            ),
        ]
    )
    ctx = AgentRunContext(
        session_id="s1",
        agent_id="hub",
        db=None,
        llm=fake,
        llm_config=None,
        memory=None,
        tool_registry=FakeToolRegistry(
            schemas=[{"function": {"name": "dispatch_agent"}}],
            results={"dispatch_agent": dispatch},
        ),
        extra={},
    )
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake, ctx=ctx)

    assert result is not None
    assert result.dispatches == [dispatch]
    assert result.iterations == 1
    # 有 dispatch 时不触发收口补写
    assert "[收口]" not in join_sse(chunks)


# —— CoT 两阶段 ——

def test_run_cot_two_phase_channels():
    agent_def = _agent(id="mentor", workflow="cot")
    fake = FakeLLM(
        stream_scripts=[
            # 阶段 1:thinking 通道
            [LLMChunk(type="text", text="思路要点"), LLMChunk(type="done", usage={"total_tokens": 10})],
            # 阶段 2:text 通道
            [LLMChunk(type="text", text="正文内容"), LLMChunk(type="done", usage={"total_tokens": 20})],
        ]
    )
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake)

    # 思路进 thinking 通道
    think_events = [c for c in chunks if "event: thinking" in c and "思路要点" in c]
    assert think_events
    # 正文进 text_delta 通道
    text_events = [c for c in chunks if "event: text_delta" in c and "正文内容" in c]
    assert text_events
    assert result is not None
    assert result.text == "正文内容"
    assert result.iterations == 2
    assert result.usage.get("total_tokens") == 30  # 两阶段 usage 累加


def test_run_cot_phase1_failed_aborts():
    agent_def = _agent(id="mentor", workflow="cot")
    fake = FakeLLM(
        stream_scripts=[
            [LLMChunk(type="error", error="网络断了")],
        ]
    )
    engine = ReActEngine()
    chunks, result, _ = _collect(engine, agent_def, fake)

    assert result is not None
    assert result.iterations == 1
    assert any('"failed": true' in c for c in chunks)
    # phase1 失败后不再进入 phase2(只调了一次流式)
    assert len(fake.calls) == 1
