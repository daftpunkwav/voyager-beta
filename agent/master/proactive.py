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
from agent.runtime.observability import is_quota_exceeded_reply
from agent.runtime.scheduler import Scheduler


@dataclass(frozen=True)
class ProactiveBudget:
    per_session: int = 3
    per_day: int = 10
    follow_up_max: int = 2
    quiet_start: int = 23  # 安静时段 [quiet_start, quiet_end)
    quiet_end: int = 7


def _to_int(value, default: int) -> int:
    """把 setting 值转 int;0 是合法开关值,不能当 falsy 丢掉。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        settings=None,  # 可选设置句柄(有 get(key) 即可):预算热读当前值(§9.8)
        meter=None,  # 可选计量句柄(有 tokens_used_today() 即可):配额预检(§9.9)
    ) -> None:
        self._bus = bus
        self._llm = llm
        self._memory = memory
        self._scheduler = scheduler
        self.budget = budget or ProactiveBudget()
        self._clock = clock
        self._settings = settings
        self._meter = meter
        self._session_sent = 0
        self._day_sent: dict[str, int] = {}
        self._followups_sent = 0
        self._followup_timer = ""

    def _current_budget(self) -> ProactiveBudget:
        """本次判定用的预算:有 settings 句柄则热读当前值,没有则用构造时快照。"""
        if self._settings is None:
            return self.budget
        return ProactiveBudget(
            per_session=_to_int(self._settings.get("agent.proactive.per_session"), self.budget.per_session),
            per_day=_to_int(self._settings.get("agent.proactive.per_day"), self.budget.per_day),
            follow_up_max=_to_int(self._settings.get("agent.proactive.follow_up_max"), self.budget.follow_up_max),
            quiet_start=_to_int(self._settings.get("agent.proactive.quiet_start"), self.budget.quiet_start),
            quiet_end=_to_int(self._settings.get("agent.proactive.quiet_end"), self.budget.quiet_end),
        )

    def can_send(self) -> bool:
        """预算与安静时段检查(§9.8)。"""
        budget = self._current_budget()
        hour = time.localtime(self._clock()).tm_hour
        quiet = (
            hour >= budget.quiet_start or hour < budget.quiet_end
            if budget.quiet_start > budget.quiet_end
            else budget.quiet_start <= hour < budget.quiet_end
        )
        if quiet:
            return False
        day = time.strftime("%Y-%m-%d", time.localtime(self._clock()))
        if self._day_sent.get(day, 0) >= budget.per_day:
            return False
        return self._session_sent < budget.per_session

    def would_exceed_quota(self) -> bool:
        """token 日配额预检(§9.9):当日已用达到上限即 True。

        只做 proactive 自己的预检,避免配额满时还发起一次注定被拒的
        complete;不复制 metered_llm 的计量/包装逻辑。meter 或 settings
        缺席时无法预检,返回 False(仍靠回复检测兜底)。
        """
        if self._meter is None or self._settings is None:
            return False
        try:
            limit = int(self._settings.get("agent.resource.daily_tokens") or 0)
        except (TypeError, ValueError):
            limit = 0  # 脏值当不限,与 metered_llm 的容错同风格
        if limit <= 0:
            return False
        return self._meter.tokens_used_today() >= limit

    async def on_user_online(self, *, trace_id: str = "") -> str | None:
        """用户上线:根据记忆生成首条问候(§9.8)。被预算/配额拦截则返回 None。

        配额双保险:先 would_exceed_quota 预检(不发 complete);问候文案若
        仍检出配额降级句(理论不可达,防 _compose_greeting 逻辑回退)也不发。
        成功发出问候后挂追问链;被拦截时则不挂。
        """
        if not self.can_send():
            return None
        if self.would_exceed_quota():
            return None
        text = await self._compose_greeting()
        if is_quota_exceeded_reply(text):
            return None
        await self._send(
            text,
            kind="greeting",
            reason="你打开了应用",
            trace_id=trace_id,
        )
        self.schedule_followup(trace_id=trace_id)
        return text

    def notify_user_reply(self) -> None:
        """用户回复了:取消追问链,重置计数。"""
        if self._followup_timer:
            self._scheduler.cancel_timer(self._followup_timer)
            self._followup_timer = ""
        self._followups_sent = 0

    def schedule_followup(self, *, delay_s: float = 180.0, trace_id: str = "") -> None:
        """发出一条消息且未获回复后调用:delay 后追问,链上限 follow_up_max。

        再次调度前取消未触发的旧定时器,避免 user.online 重复时泄漏同名 task。
        """
        budget = self._current_budget()
        if self._followup_timer:
            self._scheduler.cancel_timer(self._followup_timer)
            self._followup_timer = ""
        if self._followups_sent >= budget.follow_up_max:
            return

        async def _followup() -> None:
            current_budget = self._current_budget()
            # 配额满与预算/安静时段同口径拦截(§9.9 尾刀):不发 followup、
            # 也不递归挂下一条,避免配额满时留一条空转定时器链
            if (
                self._followups_sent >= current_budget.follow_up_max
                or not self.can_send()
                or self.would_exceed_quota()
            ):
                return
            self._followups_sent += 1
            await self._send(
                "怎么不回我?还在忙吗?有需要随时说一声。",
                kind="followup",
                reason="你一段时间没回复",
                trace_id=trace_id,
            )
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
            # 配额降级句不当问候发(§9.9):回落静态默认句,与无 LLM 时一致
            if reply.text and not is_quota_exceeded_reply(reply.text):
                return reply.text
        return "欢迎回来。要继续上次的事,还是开始点新的?"

    async def _send(self, text: str, *, kind: str, reason: str, trace_id: str = "") -> None:
        """发出主动消息。kind/reason 是用户可见出处(§9.8/§10.2):
        reason 是写死的触发源短句,不是 LLM 生成的解释。"""
        self._session_sent += 1
        day = time.strftime("%Y-%m-%d", time.localtime(self._clock()))
        self._day_sent[day] = self._day_sent.get(day, 0) + 1
        if self._bus is not None:
            await self._bus.publish(
                Event(
                    type=DomainEvent.AGENT_MESSAGE,
                    actor=AGENT_MAIN,
                    payload={"content": text, "proactive": True, "kind": kind, "reason": reason},
                    trace_id=trace_id,
                )
            )
