"""七种模式的执行策略(§9.4.2)。

统一签名:run_mode(mode, ...) 按模式分发;Lucien 强制 ReAct(决策 §15)。
轮数与工具上限是两个独立上限(§9.19),超限体面中断并说明如何提高。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.llm import LLMClient
from agent.tools.base import Toolbelt

# ReAct 续步:零 tool_call 的文本不是合法终局(寒暄除外)。
# 不扫描「好/这就去办」——那是模型终局,不是循环条件。
_CONTINUE_MARK = "[react]"
_CONTINUE_TEXT = (
    f"{_CONTINUE_MARK} Observation: 本回合尚未产生 tool call。"
    "继续 Action:调用工具;若不需要工具,用一句话说明原因。"
)
_CHITCHAT_RE = re.compile(
    r"^(你好|嗨|哈喽|在吗|早上好|晚上好|谢谢|感谢|嗯+|ok|okay|好)$",
    re.IGNORECASE,
)


class Mode(str, Enum):
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    COT = "cot"
    TOT = "tot"
    GOT = "got"
    REFLEXION = "reflexion"
    DIRECT = "direct"


@dataclass(frozen=True)
class ModeLimits:
    max_rounds: int = 20
    max_tool_calls: int = 40


StepCb = Callable[[str, str, str], Awaitable[None]]  # (kind, name, summary)


async def _noop_step(kind: str, name: str, summary: str) -> None:
    return None


async def run_mode(
    mode: Mode,
    *,
    llm: LLMClient,
    toolbelt: Toolbelt | None,
    messages: list[dict[str, Any]],
    limits: ModeLimits,
    on_step: StepCb = _noop_step,
    continue_if_idle: bool = False,
) -> str:
    if mode is Mode.DIRECT:
        reply = await llm.complete(messages)
        return reply.text or ""
    if mode is Mode.COT:
        return await run_mode(
            Mode.DIRECT,
            llm=llm,
            toolbelt=None,
            messages=[*_sys("请先逐步推理,再给出结论。"), *messages],
            limits=limits,
        )
    if mode is Mode.REACT:
        return await _react(
            llm, toolbelt, messages, limits, on_step,
            continue_if_idle=continue_if_idle,
        )
    if mode is Mode.PLAN_EXECUTE:
        plan = await llm.complete([*_sys("先给出分步执行计划,不要调用工具。"), *messages])
        await on_step("llm", "plan", (plan.text or "")[:120])
        messages = [*messages, {"role": "assistant", "content": plan.text or ""}]
        return await _react(llm, toolbelt, messages, limits, on_step)
    if mode is Mode.REFLEXION:
        draft = await _react(llm, toolbelt, messages, limits, on_step)
        review = await llm.complete(
            [*messages, {"role": "assistant", "content": draft},
             *_sys("审视上面的草稿:指出问题并给出修订版。")]
        )
        await on_step("llm", "reflexion", "自我审视并修订")
        return review.text or draft
    if mode is Mode.TOT:
        return await _branch(llm, messages, on_step, branches=3, joint=False)
    if mode is Mode.GOT:
        return await _branch(llm, messages, on_step, branches=2, joint=True)
    raise ValueError(f"未知模式: {mode}")


def _sys(content: str) -> list[dict[str, Any]]:
    return [{"role": "system", "content": content}]


async def _react(
    llm: LLMClient,
    toolbelt: Toolbelt | None,
    messages: list[dict[str, Any]],
    limits: ModeLimits,
    on_step: StepCb,
    *,
    continue_if_idle: bool = False,
) -> str:
    """推理-行动循环:有 tool_calls 时自行连打 complete,直到模型给出 Final Answer。

    纯文本且本回合还没有任何 Action 时,不把这当成结束(寒暄除外)——
    这是 loop 的退出条件,不是去扫描「好/这就去办」。
    specs 每轮 complete 前重取(phase-06 域激活)。成对回填形状不变(§9.1)。
    """
    tool_calls_used = 0
    for round_n in range(1, limits.max_rounds + 1):
        specs = toolbelt.specs() if toolbelt is not None else None
        reply = await llm.complete(messages, specs)
        await on_step(
            "llm",
            f"round-{round_n}",
            (reply.text or f"{len(reply.tool_calls)} 个工具调用")[:120],
        )
        if reply.final:
            text = reply.text or ""
            # 有 tool_calls 时本函数不会走到这里,loop 已在自行连打 API。
            # 纯文本 = 模型宣告 Final Answer。尚未产生过 Action 的非寒暄回合
            # 不算结束,把文本当作 Thought 写回 transcript 再 complete 一次。
            if (
                continue_if_idle
                and round_n < limits.max_rounds
                and _should_continue_react(messages, tool_calls_used)
            ):
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": _CONTINUE_TEXT})
                continue
            return text
        if toolbelt is None:
            return reply.text or "[无工具可用] LLM 请求了工具但未授予"
        # 工具上限截断:未执行的 call 不进 assistant.tool_calls,避免"有 call 无 result"被端点 400
        pending = list(reply.tool_calls)
        if tool_calls_used + len(pending) > limits.max_tool_calls:
            pending = pending[: limits.max_tool_calls - tool_calls_used]
        if not pending:
            return (
                f"[中断] 已达工具调用上限({limits.max_tool_calls});"
                "可在设置提高 agent.rounds.tool_max"
            )
        # 中性回填:一条 assistant 带本轮 tool_calls(含 id),随后每条结果带同一 tool_call_id;
        # 各家线格式(OpenAI tool_call_id / Anthropic tool_use_id)由 services/llm client 翻译
        messages.append({
            "role": "assistant",
            "content": reply.text or "",
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in pending
            ],
        })
        for call in pending:
            result = await toolbelt.call(call)
            tool_calls_used += 1
            await on_step("tool", call.name, result[:120])
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": result,
            })
        if len(pending) < len(reply.tool_calls):
            return (
                f"[中断] 已达工具调用上限({limits.max_tool_calls});"
                "可在设置提高 agent.rounds.tool_max"
            )
    return f"[中断] 已达 ReAct 轮数上限({limits.max_rounds});可在设置提高 agent.rounds.max"


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        content = str(m.get("content") or "")
        if _CONTINUE_MARK in content:
            continue
        return content.strip()
    return ""


def _should_continue_react(
    messages: list[dict[str, Any]], tool_calls_used: int,
) -> bool:
    """纯文本终局且本回合还没有任何 Action → 继续同一 ReAct loop。

    不读 assistant 文案(不抓「好/马上」)。寒暄允许零工具结束;已续过一步
    则尊重第二次纯文本(模型明确说不需要工具)。
    """
    if tool_calls_used > 0:
        return False
    if any(_CONTINUE_MARK in str(m.get("content") or "") for m in messages):
        return False
    user = _last_user_text(messages)
    if not user or _CHITCHAT_RE.match(user):
        return False
    return True


async def _branch(
    llm: LLMClient,
    messages: list[dict[str, Any]],
    on_step: StepCb,
    *,
    branches: int,
    joint: bool,
) -> str:
    """ToT:多候选择优;GoT:多角度产出后聚合(多源聚合,决策 §15)。"""
    hint = "从不同来源/角度各自作答,最后再合并。" if joint else "给出一种候选解答。"
    prompts = [[*_sys(f"{hint}(第 {i + 1} 路)"), *messages] for i in range(branches)]
    candidates = await asyncio.gather(*(llm.complete(p) for p in prompts))
    texts = [c.text or "" for c in candidates]
    await on_step("llm", "branch", f"{branches} 路产出完成")
    merge_prompt = (
        "把上面几路产出合并为一致、完整的最终答案。"
        if joint
        else "评估上面几个候选,选出最优并润色为最终答案。"
    )
    final = await llm.complete(
        [
            *messages,
            *[{"role": "assistant", "content": t, "name": f"branch-{i}"} for i, t in enumerate(texts)],
            *_sys(merge_prompt),
        ]
    )
    return final.text or texts[0]
