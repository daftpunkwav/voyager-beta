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
        # 中性回填(§9.1):assistant 带 tool_calls,结果带同一 id,顺序 user→assistant→tool
        assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
        assert messages[1]["tool_calls"] == [
            {"id": "1", "name": "echo_tool", "arguments": {"x": "a"}}
        ]
        assert messages[2]["tool_call_id"] == "1"
        assert messages[2]["content"] == "echo:a"

    async def test_multiple_calls_paired_in_order(self) -> None:
        """一轮多个 call:一条 assistant + 多条 tool,顺序一致,中间不插入 user/system。"""
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("1", "echo_tool", {"x": "a"}),
                        ToolCall("2", "echo_tool", {"x": "b"}),
                    )
                ),
                LLMReply(text="完成"),
            ]
        )
        messages = _msgs()
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=_belt(), messages=messages, limits=ModeLimits()
        )
        assert result == "完成"
        assert [m["role"] for m in messages] == ["user", "assistant", "tool", "tool"]
        assert messages[1]["tool_calls"] == [
            {"id": "1", "name": "echo_tool", "arguments": {"x": "a"}},
            {"id": "2", "name": "echo_tool", "arguments": {"x": "b"}},
        ]
        assert [m["tool_call_id"] for m in messages[2:]] == ["1", "2"]

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
        messages = _msgs()
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=messages,
            limits=ModeLimits(max_tool_calls=1),
        )
        assert result.startswith("[中断] 已达工具调用上限")
        # 截断:只执行第一个 call,assistant.tool_calls 不含未执行的 "2",不留"有 call 无 result"
        assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
        assert [tc["id"] for tc in messages[1]["tool_calls"]] == ["1"]
        assert messages[2]["tool_call_id"] == "1"

    async def test_tool_calls_without_toolbelt(self) -> None:
        llm = FakeLLM([LLMReply(tool_calls=(ToolCall("1", "echo_tool", {}),))])
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert "无工具可用" in result

    async def test_zero_tool_final_continues_react_loop(self) -> None:
        """非寒暄 + 零 tool_call 的文本不是终局:同一 loop 再 complete,不扫描「好」。"""
        llm = FakeLLM(
            [
                LLMReply(text="行。"),  # 不含「马上/这就去办」
                LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "a"}),)),
                LLMReply(text="echo 完了"),
            ]
        )
        messages = [{"role": "user", "content": "都测试一下"}]
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=_belt(), messages=messages,
            limits=ModeLimits(), continue_if_idle=True,
        )
        assert result == "echo 完了"
        assert len(llm.calls) == 3
        assert any("[react]" in str(m.get("content", "")) for m in messages)

    async def test_compresses_over_budget_before_complete(self) -> None:
        """每轮 complete 前压缩(phase-15):超预算的旧 tool 结果被截断,system 保留。"""
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "任务"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
            {"role": "tool", "tool_call_id": "a", "content": "旧结果" * 9000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "b"}]},
            {"role": "tool", "tool_call_id": "b", "content": "次新结果" * 9000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c"}]},
            {"role": "tool", "tool_call_id": "c", "content": "最新结果" * 9000},
            {"role": "user", "content": "收尾"},
        ]
        llm = FakeLLM([LLMReply(text="完成")])
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=None, messages=messages, limits=ModeLimits()
        )
        assert result == "完成"
        sent = llm.calls[0]["messages"]
        assert sent[0]["role"] == "system" and sent[0]["content"] == "系统提示"
        assert "已压缩" in sent[3]["content"] and len(sent[3]["content"]) < 200
        assert sent[5]["content"] == "次新结果" * 9000  # 最近 4 条内不动
        assert sent[7]["content"] == "最新结果" * 9000
        assert len(sent) == len(messages)  # 只截断不剪条目:tool 对保持成对

    async def test_chitchat_without_tools_does_not_nudge(self) -> None:
        llm = FakeLLM([LLMReply(text="你好,我在。")])
        messages = [{"role": "user", "content": "你好"}]
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=_belt(), messages=messages,
            limits=ModeLimits(), continue_if_idle=True,
        )
        assert result == "你好,我在。"
        assert len(llm.calls) == 1


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
