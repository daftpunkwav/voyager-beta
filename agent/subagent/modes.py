"""七种模式的执行策略(§9.4.2)。

统一签名:run_mode(mode, ...) 按模式分发;Lucien 强制 ReAct(决策 §15)。
轮数与工具上限是两个独立上限(§9.19),超限体面中断并说明如何提高。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.llm import LLMClient
from agent.tools.base import Toolbelt


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
        return await _react(llm, toolbelt, messages, limits, on_step)
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
) -> str:
    """推理-行动循环:工具结果回填 messages,直到 LLM 给出最终文本。"""
    specs = toolbelt.specs() if toolbelt is not None else None
    tool_calls_used = 0
    for round_n in range(1, limits.max_rounds + 1):
        reply = await llm.complete(messages, specs)
        await on_step(
            "llm",
            f"round-{round_n}",
            (reply.text or f"{len(reply.tool_calls)} 个工具调用")[:120],
        )
        if reply.final:
            return reply.text or ""
        if toolbelt is None:
            return reply.text or "[无工具可用] LLM 请求了工具但未授予"
        for call in reply.tool_calls:
            if tool_calls_used >= limits.max_tool_calls:
                return (
                    f"[中断] 已达工具调用上限({limits.max_tool_calls});"
                    "可在设置提高 agent.rounds.tool_max"
                )
            result = await toolbelt.call(call)
            tool_calls_used += 1
            await on_step("tool", call.name, result[:120])
            messages.append({"role": "tool", "name": call.name, "content": result})
    return f"[中断] 已达 ReAct 轮数上限({limits.max_rounds});可在设置提高 agent.rounds.max"


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
