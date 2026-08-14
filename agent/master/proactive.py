"""主动触达(§9.8):问候、追问与防轰炸。

- 上线问候:基于画像/近期情节生成,fire-and-forget;
- 追问:用户未回复时一次性定时器补一条,追问链上限 2 条(决策 §15);
- 防轰炸预算器:每会话/每日上限 + 安静时段,全部是可调设置项(§8.8)。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventBus

from agent.llm import LLMClient
from agent.memory import Memory
from agent.runtime.events import AGENT_MAIN
from agent.runtime.scheduler import Scheduler


@dataclass(frozen=True)
class ProactiveBudget:
    per_session: int = 3
    per_day: int = 10
    follow_up_max: int = 2
    quiet_start: int = 23  # 安静时段 [quiet_start, quiet_end)
    quiet_end: int = 7


class ProactiveEngine:
    def __init__(
        self,
        *,
        bus: EventBus | None,
        llm: LLMClient | None,
        memory: Memory | None,
        scheduler: Scheduler,
        budget: ProactiveBudget | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._bus = bus
        self._llm = llm
        self._memory = memory
        self._scheduler = scheduler
        self.budget = budget or ProactiveBudget()
        self._clock = clock
        self._session_sent = 0
        self._day_sent: dict[str, int] = {}
        self._followups_sent = 0
        self._followup_timer = ""

    def can_send(self) -> bool:
        """预算与安静时段检查(§9.8)。"""
        hour = time.localtime(self._clock()).tm_hour
        quiet = (
            hour >= self.budget.quiet_start or hour < self.budget.quiet_end
            if self.budget.quiet_start > self.budget.quiet_end
            else self.budget.quiet_start <= hour < self.budget.quiet_end
        )
        if quiet:
            return False
        day = time.strftime("%Y-%m-%d", time.localtime(self._clock()))
        if self._day_sent.get(day, 0) >= self.budget.per_day:
            return False
        return self._session_sent < self.budget.per_session

    async def on_user_online(self, *, trace_id: str = "") -> str | None:
        """用户上线:根据记忆生成首条问候(§9.8)。被预算拦截则返回 None。"""
        if not self.can_send():
            return None
        text = await self._compose_greeting()
        await self._send(text, trace_id=trace_id)
        return text

    def notify_user_reply(self) -> None:
        """用户回复了:取消追问链,重置计数。"""
        if self._followup_timer:
            self._scheduler.cancel_timer(self._followup_timer)
            self._followup_timer = ""
        self._followups_sent = 0

    def schedule_followup(self, *, delay_s: float = 180.0, trace_id: str = "") -> None:
        """发出一条消息且未获回复后调用:delay 后追问,链上限 follow_up_max。"""
        if self._followups_sent >= self.budget.follow_up_max:
            return

        async def _followup() -> None:
            if self._followups_sent >= self.budget.follow_up_max or not self.can_send():
                return
            self._followups_sent += 1
            await self._send("怎么不回我?还在忙吗?🙂", trace_id=trace_id)
            self.schedule_followup(delay_s=delay_s * 2, trace_id=trace_id)

        self._followup_timer = self._scheduler.call_later(
            delay_s, _followup, name="proactive-followup"
        )

    async def _compose_greeting(self) -> str:
        context = ""
        if self._memory is not None:
            context = self._memory.profile.render()
        if self._llm is not None:
            reply = await self._llm.complete(
                [
                    {"role": "system", "content": "你是常驻助手。根据用户画像写一句简短的上线问候,"
                     "可提及最近在忙的事。不超过 60 字。"},
                    {"role": "user", "content": context or "(无画像)"},
                ]
            )
            if reply.text:
                return reply.text
        return "欢迎回来。要继续上次的事,还是开始点新的?"

    async def _send(self, text: str, *, trace_id: str = "") -> None:
        self._session_sent += 1
        day = time.strftime("%Y-%m-%d", time.localtime(self._clock()))
        self._day_sent[day] = self._day_sent.get(day, 0) + 1
        if self._bus is not None:
            await self._bus.publish(
                Event(
                    type=DomainEvent.AGENT_MESSAGE,
                    actor=AGENT_MAIN,
                    payload={"content": text, "proactive": True},
                    trace_id=trace_id,
                )
            )
