"""主动触达测试(§9.8):上线问候、防轰炸预算、安静时段、追问链。"""

import asyncio
import time

from platform_contracts import DomainEvent
from platform_eventbus import EventBus, EventLog

from agent.llm import FakeLLM
from agent.master.proactive import ProactiveBudget, ProactiveEngine
from agent.runtime.scheduler import Scheduler
from agent.tools.reach_out import reach_out_tool


def _clock(hour: int):
    # mktime 按本地时区解释,与 ProactiveEngine 内部 localtime 口径一致
    return lambda: time.mktime((2026, 8, 14, hour, 0, 0, 0, 0, -1))


class _FakeSettings:
    """有 get(key) 的 settings 句柄,供热读测试用。"""

    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)


def _engine(tmp_path, *, hour: int = 12, budget: ProactiveBudget | None = None, settings=None):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    engine = ProactiveEngine(
        bus=bus,
        llm=FakeLLM(default="欢迎回来,接着看 langgraph 吗?"),
        memory=None,
        scheduler=Scheduler(),
        budget=budget or ProactiveBudget(),
        clock=_clock(hour),
        settings=settings,
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
        # 出处(§9.8/§10.2):问候的触发源写死,不是 LLM 生成的解释
        assert msgs[0]["kind"] == "greeting"
        assert msgs[0]["reason"] == "你打开了应用"

    async def test_greeting_schedules_followup(self, tmp_path) -> None:
        """问候成功后挂追问链;用户回复后取消,不应出现 followup 消息。"""
        engine, log = _engine(tmp_path)
        await engine.on_user_online()
        assert engine._followup_timer != ""
        engine.notify_user_reply()
        await asyncio.sleep(0.05)
        msgs = _messages(log)
        assert len(msgs) == 1 and msgs[0]["kind"] == "greeting"
        assert all(m["kind"] != "followup" for m in msgs)

    async def test_quiet_hours_block(self, tmp_path) -> None:
        engine, log = _engine(tmp_path, hour=2)  # 凌晨 2 点,安静时段内
        assert await engine.on_user_online() is None
        assert _messages(log) == []

    async def test_session_budget_exhausted(self, tmp_path) -> None:
        engine, log = _engine(tmp_path, budget=ProactiveBudget(per_session=1))
        await engine.on_user_online()
        assert await engine.on_user_online() is None  # 第二次被预算拦截
        assert len(_messages(log)) == 1

    async def test_hot_read_per_session_zero_blocks_greeting(self, tmp_path) -> None:
        """热读:构造时 per_session=3,但 settings 里改为 0,问候应被拦截。"""
        settings = _FakeSettings({"agent.proactive.per_session": 0})
        engine, log = _engine(tmp_path, budget=ProactiveBudget(per_session=3), settings=settings)
        assert await engine.on_user_online() is None
        assert _messages(log) == []

    async def test_hot_read_per_session_zero_cancels_followup(self, tmp_path) -> None:
        """热读:构造时 per_session=1 已通过问候,再把 settings 改成 0,第二次问候被拦截。"""
        settings = _FakeSettings({"agent.proactive.per_session": 1})
        engine, log = _engine(tmp_path, budget=ProactiveBudget(per_session=1), settings=settings)
        await engine.on_user_online()
        settings._values["agent.proactive.per_session"] = 0
        assert await engine.on_user_online() is None
        assert len(_messages(log)) == 1


class TestFollowUp:
    async def test_followup_chain_capped_at_two(self, tmp_path) -> None:
        engine, log = _engine(tmp_path)
        engine.schedule_followup(delay_s=0.02)
        await asyncio.sleep(0.3)  # 0.02 → 0.04,链到上限即停
        msgs = _messages(log)
        assert len(msgs) == 2
        # 每条追问都带出处(§9.8)
        assert all(m["kind"] == "followup" for m in msgs)
        assert all(m["reason"] == "你一段时间没回复" for m in msgs)

    async def test_user_reply_cancels_chain(self, tmp_path) -> None:
        engine, log = _engine(tmp_path)
        engine.schedule_followup(delay_s=0.05)
        engine.notify_user_reply()  # 用户回复了:取消追问
        await asyncio.sleep(0.15)
        assert _messages(log) == []

    async def test_follow_up_max_zero_skips_timer(self, tmp_path) -> None:
        """追问链上限为 0 时,schedule_followup 不挂 timer。"""
        engine, log = _engine(tmp_path, budget=ProactiveBudget(follow_up_max=0))
        engine.schedule_followup(delay_s=0.01)
        assert engine._followup_timer == ""
        await asyncio.sleep(0.05)
        assert _messages(log) == []

    async def test_hot_read_follow_up_max_zero_skips_timer(self, tmp_path) -> None:
        """热读:构造时 follow_up_max=2,但 settings 里改为 0,不挂 timer。"""
        settings = _FakeSettings({"agent.proactive.follow_up_max": 0})
        engine, log = _engine(tmp_path, budget=ProactiveBudget(follow_up_max=2), settings=settings)
        engine.schedule_followup(delay_s=0.01)
        assert engine._followup_timer == ""
        await asyncio.sleep(0.05)
        assert _messages(log) == []

    async def test_reschedule_cancels_previous_timer(self, tmp_path) -> None:
        """再次 schedule 会取消未触发的旧定时器,避免重复 user.online 双响。"""
        engine, log = _engine(tmp_path, budget=ProactiveBudget(follow_up_max=1))
        engine.schedule_followup(delay_s=0.2)
        engine.schedule_followup(delay_s=0.02)
        await asyncio.sleep(0.08)
        msgs = _messages(log)
        assert len(msgs) == 1 and msgs[0]["kind"] == "followup"


class TestReachOut:
    """reach_out 工具(fire-and-forget,不走 ProactiveEngine 预算)带出处 payload。"""

    async def test_blank_reason_falls_back_to_default(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        handler = reach_out_tool(bus)["reach_out"].handler
        await handler("顺手帮你把索引建好了")
        msgs = _messages(log)
        assert len(msgs) == 1
        assert msgs[0]["proactive"] is True
        assert msgs[0]["kind"] == "reach_out"
        assert msgs[0]["reason"] == "Agent 主动联系"

    async def test_reason_passthrough_when_given(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        handler = reach_out_tool(bus)["reach_out"].handler
        await handler("在吗", reason="  你在学图谱  ")  # 去空白后采用调用方的
        msgs = _messages(log)
        assert msgs[0]["kind"] == "reach_out"
        assert msgs[0]["reason"] == "你在学图谱"
