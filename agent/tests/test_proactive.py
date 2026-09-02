"""主动触达测试(§9.8):上线问候、防轰炸预算、安静时段、追问链、配额拦截(§9.9)。"""

import asyncio
import time

from platform_contracts import DomainEvent
from platform_eventbus import EventBus, EventLog

from agent.llm import FakeLLM
from agent.master.proactive import ProactiveBudget, ProactiveEngine
from agent.runtime import Meter, MeterRecord
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


def _engine(tmp_path, *, hour: int = 12, budget: ProactiveBudget | None = None,
            settings=None, meter=None):
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
        meter=meter,
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


class TestQuotaGuard:
    """配额双保险(phase-65,§9.9):预检拦截 + 降级句不当问候发。"""

    async def test_quota_full_blocks_greeting_before_llm(self, tmp_path) -> None:
        """配额满 + 预算允许:预检拦截,不发问候、不碰 LLM、不挂追问链。"""
        meter = Meter()
        meter.record(MeterRecord(kind="llm", name="default", ms=1.0, input_tokens=50))
        settings = _FakeSettings({"agent.resource.daily_tokens": 50})
        engine, log = _engine(tmp_path, settings=settings, meter=meter)
        assert engine.would_exceed_quota() is True
        assert await engine.on_user_online() is None
        assert _messages(log) == []
        assert engine._llm.calls == []
        assert engine._followup_timer == ""

    async def test_quota_full_blocks_followup_chain(self, tmp_path) -> None:
        """配额满(§9.9 尾刀):问候被拦;手动挂追问链,定时器触发也不发 followup。"""
        meter = Meter()
        meter.record(MeterRecord(kind="llm", name="default", ms=1.0, input_tokens=50))
        settings = _FakeSettings({"agent.resource.daily_tokens": 50})
        engine, log = _engine(tmp_path, settings=settings, meter=meter)
        assert await engine.on_user_online() is None  # 问候被拦
        engine.schedule_followup(delay_s=0.02)
        await asyncio.sleep(0.3)  # 覆盖两条链的时长:触发时配额满,一条也不发、不续链
        assert _messages(log) == []
        assert engine._followups_sent == 0

    async def test_quota_headroom_greeting_unaffected(self, tmp_path) -> None:
        """配额未满:问候照常发出、文案不回落。"""
        meter = Meter()
        meter.record(MeterRecord(kind="llm", name="default", ms=1.0, input_tokens=10))
        settings = _FakeSettings({"agent.resource.daily_tokens": 50})
        engine, log = _engine(tmp_path, settings=settings, meter=meter)
        assert engine.would_exceed_quota() is False
        text = await engine.on_user_online()
        assert text == "欢迎回来,接着看 langgraph 吗?"
        assert len(_messages(log)) == 1

    async def test_quota_reply_falls_back_to_static_greeting(self, tmp_path) -> None:
        """无 meter 可预检时,LLM 返回的配额降级句不当问候发,回落静态默认句。"""
        settings = _FakeSettings({"agent.resource.daily_tokens": 50})
        log = EventLog(tmp_path / "events.db")
        engine = ProactiveEngine(
            bus=EventBus(log),
            llm=FakeLLM(default=(
                "（今日 LLM token 配额已用完:明天自动恢复,或在设置里调高/关闭日配额。）"
            )),
            memory=None,
            scheduler=Scheduler(),
            clock=_clock(12),
            settings=settings,
        )
        text = await engine.on_user_online()
        assert text == "欢迎回来。要继续上次的事,还是开始点新的?"
        msgs = _messages(log)
        assert len(msgs) == 1
        assert "配额" not in msgs[0]["content"]


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
