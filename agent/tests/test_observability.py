"""可观测与 token 日配额(phase-60,§9.9 资源维)。

- Meter.tokens_used_today:UTC 自然日切分,跨日不累计;
- metered_llm:配额 0 不限、未超限放行并计量、已超限拒真实调用(降级文本);
- build_agent 接线:主对话(直聊 / ReAct 实例)的 LLM 走包装层。
"""

import time
from datetime import UTC, datetime

from platform_contracts import LOCAL_USER

from agent.llm import FakeLLM, LLMReply, Usage
from agent.main import build_agent
from agent.master.arbiter import ArbiterMode
from agent.runtime import Meter, MeterRecord, metered_llm


def _ts(*args: int) -> float:
    """UTC (年,月,日,时,分) → epoch 秒;测试里写死时刻用。"""
    y, mo, d, h, mi = args
    return datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


def _rec(kind: str = "llm", name: str = "default", ms: float = 1.0,
         inp: int = 0, out: int = 0, ts: float | None = None) -> MeterRecord:
    # 默认 ts 取当前时刻:预塞记录算「今天」,才能被 tokens_used_today 计到
    return MeterRecord(kind=kind, name=name, ms=ms,
                       input_tokens=inp, output_tokens=out,
                       ts=ts if ts is not None else time.time())


class TestTokensUsedToday:
    def test_sums_same_utc_day(self) -> None:
        meter = Meter()
        meter.record(_rec(inp=100, out=20, ts=_ts(2026, 1, 15, 8, 0)))
        meter.record(_rec(inp=50, ts=_ts(2026, 1, 15, 23, 59)))
        meter.record(_rec(inp=999, ts=_ts(2026, 1, 10, 12, 0)))  # 更早的日期
        assert meter.tokens_used_today(now=_ts(2026, 1, 15, 12, 0)) == 170

    def test_crosses_utc_midnight(self) -> None:
        meter = Meter()
        meter.record(_rec(inp=100, ts=_ts(2026, 1, 15, 23, 59)))  # 昨日(UTC)
        meter.record(_rec(inp=40, out=10, ts=_ts(2026, 1, 16, 0, 1)))  # 今日
        assert meter.tokens_used_today(now=_ts(2026, 1, 16, 8, 0)) == 50
        assert meter.tokens_used_today(now=_ts(2026, 1, 15, 23, 59)) == 100

    def test_empty_meter_is_zero(self) -> None:
        assert Meter().tokens_used_today() == 0


class TestMeteredQuota:
    """metered_llm 配额行为:complete 前热读 quota_fn,超限不碰底层。"""

    async def test_no_quota_passes_and_meters(self) -> None:
        fake = FakeLLM(default="好的")
        meter = Meter()
        metered = metered_llm(fake, meter)  # 不传 quota_fn = 不限
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "好的"
        assert len(fake.calls) == 1
        assert meter.totals()["llm_calls"] == 1

    async def test_quota_zero_means_unlimited(self) -> None:
        fake = FakeLLM(default="好的")
        meter = Meter()
        metered = metered_llm(fake, meter, quota_fn=lambda: 0)
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "好的"
        assert len(fake.calls) == 1

    async def test_under_limit_passes(self) -> None:
        fake = FakeLLM(default="好的")
        meter = Meter()
        meter.record(_rec(inp=50))  # 当日已用 50
        metered = metered_llm(fake, meter, quota_fn=lambda: 100)
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "好的"
        assert len(fake.calls) == 1

    async def test_over_limit_rejects_before_llm(self) -> None:
        fake = FakeLLM(default="好的")
        meter = Meter()
        meter.record(_rec(inp=60, out=40))  # 当日已用 100
        metered = metered_llm(fake, meter, quota_fn=lambda: 100)
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert reply.final  # 降级文本当最终回复,不打断 agent 循环
        assert "配额" in (reply.text or "")
        assert len(fake.calls) == 0  # 底层 LLM 未被调用
        # 计量里只有预塞那条,被拒调用不进 meter
        assert meter.totals()["llm_calls"] == 1

    async def test_quota_read_hot_each_call(self) -> None:
        fake = FakeLLM(dynamic=lambda m, t: LLMReply(
            text="好", usage=Usage(input_tokens=60, output_tokens=40)
        ))
        meter = Meter()
        limit = {"v": 0}
        metered = metered_llm(fake, meter, quota_fn=lambda: limit["v"])
        await metered.complete([{"role": "user", "content": "hi"}])  # 不限:放行并累计 100
        limit["v"] = 50  # 设置调小后下一句即生效
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert "配额" in (reply.text or "")
        assert len(fake.calls) == 1


class TestBuildAgentQuota:
    """build_agent 接线:主对话(master 直聊 / spawner ReAct 实例)走包装层。"""

    async def test_master_llm_quota_blocks(self, tmp_path) -> None:
        fake = FakeLLM(dynamic=lambda m, t: LLMReply(
            text="好", usage=Usage(input_tokens=60, output_tokens=40)
        ))
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=fake
        )
        try:
            await app.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            reply = await app.master._llm.complete([{"role": "user", "content": "hi"}])
            assert reply.text == "好"  # 未超限放行
            assert len(fake.calls) == 1
            reply = await app.master._llm.complete([{"role": "user", "content": "hi"}])
            assert "配额" in (reply.text or "")  # 已用 100 ≥ 100,拒绝
            assert len(fake.calls) == 1  # 底层未再被调
        finally:
            app.close()

    async def test_chat_llm_shared_by_master_and_spawner(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            # master(直聊分支)与 spawner(ReAct 实例)拿到同一个包装对象
            assert app.master._llm is app.spawner._llm
        finally:
            app.close()

    async def test_default_quota_zero(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            assert app.settings.get("agent.resource.daily_tokens") == 0
        finally:
            app.close()

    async def test_arbiter_proactive_share_metered_llm(self, tmp_path) -> None:
        """phase-64:仲裁判官与主动问候与 master 共用 chat_llm。"""
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            shared = app.master._llm
            assert app.master._arbiter._llm is shared
            assert app.proactive._llm is shared
            assert app.spawner._llm is shared
        finally:
            app.close()

    async def test_arbiter_quota_blocks_before_llm(self, tmp_path) -> None:
        fake = FakeLLM(default="enqueue")
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=fake
        )
        try:
            await app.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            app.meter.record(_rec(inp=100))  # 当日已满
            await app.master._arbiter.decide(
                "顺便帮我查天气", "写周报", mode=ArbiterMode.AUTO
            )
            assert len(fake.calls) == 0
        finally:
            app.close()

    async def test_proactive_quota_blocks_before_llm(self, tmp_path) -> None:
        fake = FakeLLM(default="你好呀")
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=fake
        )
        try:
            await app.settings.set("agent.resource.daily_tokens", 50, LOCAL_USER)
            app.meter.record(_rec(inp=50))
            # can_send 通过则进 _compose_greeting;配额满时 complete 不碰底层
            text = await app.proactive.on_user_online()
            assert len(fake.calls) == 0
            # 降级文本有内容时会当问候文案返回(phase-60 同款行为)
            assert text is not None and "配额" in text
        finally:
            app.close()
