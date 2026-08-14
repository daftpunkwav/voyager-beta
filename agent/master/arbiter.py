"""消息仲裁(§9.7):任务执行中来了新消息。

三模式(设置 agent.arbiter.mode,默认排队,决策 §15):
- queue:一律排队,当前轮结束后按序处理;
- auto:判官(LLM 短判)认为与当前任务相关 → 直接并入上下文(merge),否则排队;
- guide:判官认为相关 → merge;否则排队并提示用户("已排队,要先处理它吗?")。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.llm import LLMClient

_JUDGE_PROMPT = (
    "你是消息仲裁判官。当前任务:{goal}\n用户新消息:{text}\n"
    "若新消息与当前任务直接相关(补充信息/修正/参数),只回 merge;"
    "若是新意图,只回 enqueue。"
)


class ArbiterMode(str, Enum):
    AUTO = "auto"
    QUEUE = "queue"
    GUIDE = "guide"


@dataclass(frozen=True)
class ArbiterDecision:
    action: str  # enqueue | merge | enqueue_notify
    reason: str


class Arbiter:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def decide(
        self, new_text: str, current_goal: str, *, mode: ArbiterMode = ArbiterMode.QUEUE
    ) -> ArbiterDecision:
        if mode is ArbiterMode.QUEUE:
            return ArbiterDecision("enqueue", "排队模式:先完成当前任务")
        reply = await self._llm.complete(
            [{"role": "system", "content": _JUDGE_PROMPT.format(goal=current_goal, text=new_text)}]
        )
        verdict = (reply.text or "").strip().lower()
        related = verdict.startswith("merge")
        if related:
            return ArbiterDecision("merge", "与当前任务相关,并入上下文")
        if mode is ArbiterMode.AUTO:
            return ArbiterDecision("enqueue", "新意图,排队")
        return ArbiterDecision(
            "enqueue_notify", "新意图,已排队;如需立即处理请说'先做这个'"
        )
