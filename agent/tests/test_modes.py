"""七种模式执行策略测试(§9.4.2):ReAct 循环、轮数/工具双上限、各模式调用形态。"""

import pytest

from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.policy import PolicyEngine
from agent.subagent import Mode, ModeLimits, run_mode
from agent.tools import AgentTool, Toolbelt


def _belt() -> Toolbelt:
    async def echo_tool(x: str = "") -> str:
        return f"echo:{x}"

    return Toolbelt(
        {
            "echo_tool": AgentTool(
                name="echo_tool", description="测试工具", handler=echo_tool
            )
        },
        PolicyEngine(),
    )


def _msgs() -> list[dict]:
    return [{"role": "user", "content": "任务"}]


class TestReAct:
    async def test_tool_then_final(self) -> None:
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "a"}),)),
                LLMReply(text="完成"),
            ]
        )
        messages = _msgs()
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=_belt(), messages=messages, limits=ModeLimits()
        )
        assert result == "完成"
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs and tool_msgs[0]["content"] == "echo:a"

    async def test_rounds_limit(self) -> None:
        llm = FakeLLM(dynamic=lambda _m, _t: LLMReply(tool_calls=(ToolCall("1", "echo_tool", {}),)))
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=_msgs(),
            limits=ModeLimits(max_rounds=2),
        )
        assert result.startswith("[中断] 已达 ReAct 轮数上限")

    async def test_tool_calls_limit(self) -> None:
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(ToolCall("1", "echo_tool", {}), ToolCall("2", "echo_tool", {}))
                )
            ]
        )
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=_msgs(),
            limits=ModeLimits(max_tool_calls=1),
        )
        assert result.startswith("[中断] 已达工具调用上限")

    async def test_tool_calls_without_toolbelt(self) -> None:
        llm = FakeLLM([LLMReply(tool_calls=(ToolCall("1", "echo_tool", {}),))])
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert "无工具可用" in result


class TestOtherModes:
    async def test_direct_single_call(self) -> None:
        llm = FakeLLM([LLMReply(text="直答")])
        assert (
            await run_mode(Mode.DIRECT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits())
            == "直答"
        )
        assert len(llm.calls) == 1

    async def test_cot_prefixes_reasoning_hint(self) -> None:
        llm = FakeLLM([LLMReply(text="推理后结论")])
        await run_mode(Mode.COT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits())
        assert "逐步推理" in llm.calls[0]["messages"][0]["content"]

    async def test_plan_execute_two_phase(self) -> None:
        llm = FakeLLM([LLMReply(text="计划:1..."), LLMReply(text="执行结果")])
        result = await run_mode(
            Mode.PLAN_EXECUTE, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "执行结果"
        assert len(llm.calls) == 2
        assert llm.calls[1]["messages"][1]["content"] == "计划:1..."  # 计划回填

    async def test_reflexion_revises(self) -> None:
        llm = FakeLLM([LLMReply(text="草稿"), LLMReply(text="修订版")])
        result = await run_mode(
            Mode.REFLEXION, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "修订版"

    async def test_tot_branch_and_pick(self) -> None:
        llm = FakeLLM(
            [LLMReply(text=f"候选{i}") for i in range(3)] + [LLMReply(text="最优候选")]
        )
        result = await run_mode(
            Mode.TOT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "最优候选"
        assert len(llm.calls) == 4  # 3 候选 + 1 择优

    async def test_got_joint(self) -> None:
        llm = FakeLLM([LLMReply(text="角度A"), LLMReply(text="角度B"), LLMReply(text="合并")])
        result = await run_mode(
            Mode.GOT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "合并"
        assert len(llm.calls) == 3  # 2 角度 + 1 聚合

    async def test_unknown_mode(self) -> None:
        with pytest.raises(ValueError, match="未知模式"):
            await run_mode("nope", llm=FakeLLM(), toolbelt=None, messages=_msgs(), limits=ModeLimits())
