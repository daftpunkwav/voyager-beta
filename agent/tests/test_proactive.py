"""主动触达测试(§9.8):上线问候、防轰炸预算、安静时段、追问链。"""

import asyncio
import time

from platform_contracts import DomainEvent
from platform_eventbus import EventBus, EventLog

from agent.llm import FakeLLM
from agent.master.proactive import ProactiveBudget, ProactiveEngine
from agent.runtime.scheduler import Scheduler


def _clock(hour: int):
    # mktime 按本地时区解释,与 ProactiveEngine 内部 localtime 口径一致
    return lambda: time.mktime((2026, 8, 14, hour, 0, 0, 0, 0, -1))


def _engine(tmp_path, *, hour: int = 12, budget: ProactiveBudget | None = None):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    engine = ProactiveEngine(
        bus=bus,
        llm=FakeLLM(default="欢迎回来,接着看 langgraph 吗?"),
        memory=None,
        scheduler=Scheduler(),
        budget=budget or ProactiveBudget(),
        clock=_clock(hour),
    )
    return engine, log


def _messages(log) -> list[dict]:
    return [e.payload for _, e in log.read_after(types=[DomainEvent.AGENT_MESSAGE])]


class TestGreeting:
    async def test_online_greeting_published(self, tmp_path) -> None:
        engine, log = _engine(tmp_path)
        text = await engine.on_user_online()
        assert text == "欢迎回来,接着看 langgraph 吗?"
        msgs = _messages(log)
        assert len(msgs) == 1 and msgs[0]["proactive"] is True

    async def test_quiet_hours_block(self, tmp_path) -> None:
        engine, log = _engine(tmp_path, hour=2)  # 凌晨 2 点,安静时段内
        assert await engine.on_user_online() is None
        assert _messages(log) == []

    async def test_session_budget_exhausted(self, tmp_path) -> None:
        engine, log = _engine(tmp_path, budget=ProactiveBudget(per_session=1))
        await engine.on_user_online()
        assert await engine.on_user_online() is None  # 第二次被预算拦截
        assert len(_messages(log)) == 1


class TestFollowUp:
    async def test_followup_chain_capped_at_two(self, tmp_path) -> None:
        engine, log = _engine(tmp_path)
        engine.schedule_followup(delay_s=0.02)
        await asyncio.sleep(0.3)  # 0.02 → 0.04,链到上限即停
        assert len(_messages(log)) == 2

    async def test_user_reply_cancels_chain(self, tmp_path) -> None:
        engine, log = _engine(tmp_path)
        engine.schedule_followup(delay_s=0.05)
        engine.notify_user_reply()  # 用户回复了:取消追问
        await asyncio.sleep(0.15)
        assert _messages(log) == []
