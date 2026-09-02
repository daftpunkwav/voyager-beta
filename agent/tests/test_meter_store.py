"""Meter token 用量持久化(phase-66,§9.9 资源维):跨重启日配额不丢。

- MeterStore:按 (UTC 日, kind) 累加落 meter.db,UTC 跨日不累计;
- Meter + store:record 同步写穿透,tokens_used_today 有 store 只读 store(防双计);
- build_agent 重启:同 data_dir 重建后用量不归零、配额拦截仍生效。
"""

import time
from datetime import UTC, datetime

from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER

from agent.llm import FakeLLM, LLMReply, Usage
from agent.main import build_agent
from agent.runtime import Meter, MeterRecord, MeterStore

USER_CTX = ActorContext(actor=LOCAL_USER)


def _ts(*args: int) -> float:
    """UTC (年,月,日,时,分) → epoch 秒;测试里写死时刻用。"""
    y, mo, d, h, mi = args
    return datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


def _llm_rec(inp: int = 0, out: int = 0, ts: float | None = None) -> MeterRecord:
    return MeterRecord(kind="llm", name="default", ms=1.0,
                       input_tokens=inp, output_tokens=out,
                       ts=ts if ts is not None else _ts(2026, 1, 15, 12, 0))


class TestMeterStore:
    def test_add_and_read_today(self, tmp_path) -> None:
        store = MeterStore(tmp_path / "meter.db")
        try:
            store.add("llm", 100, 20, ts=_ts(2026, 1, 15, 8, 0))
            store.add("llm", 50, 0, ts=_ts(2026, 1, 15, 23, 0))
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 12, 0)) == 170
        finally:
            store.close()

    def test_crosses_utc_midnight(self, tmp_path) -> None:
        store = MeterStore(tmp_path / "meter.db")
        try:
            store.add("llm", 100, 0, ts=_ts(2026, 1, 15, 23, 59))
            store.add("llm", 40, 10, ts=_ts(2026, 1, 16, 0, 1))
            assert store.tokens_used_today(now=_ts(2026, 1, 16, 8, 0)) == 50
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 23, 59)) == 100
        finally:
            store.close()

    def test_reopen_keeps_totals(self, tmp_path) -> None:
        """关连接再开同一库:累计还在(持久化本质)。"""
        store = MeterStore(tmp_path / "meter.db")
        store.add("llm", 30, 12, ts=_ts(2026, 1, 15, 8, 0))
        store.close()
        store2 = MeterStore(tmp_path / "meter.db")
        try:
            assert store2.tokens_used_today(now=_ts(2026, 1, 15, 20, 0)) == 42
        finally:
            store2.close()

    def test_only_llm_kind_counted(self, tmp_path) -> None:
        """当日合计只看 llm 行(本刀 tool 不落库)。"""
        store = MeterStore(tmp_path / "meter.db")
        try:
            store.add("llm", 10, 0, ts=_ts(2026, 1, 15, 8, 0))
            store.add("tool", 999, 999, ts=_ts(2026, 1, 15, 8, 0))
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 9, 0)) == 10
        finally:
            store.close()


class TestMeterWithStore:
    def test_record_writes_through(self, tmp_path) -> None:
        """record 后 store 与 tokens_used_today 一致;内存流水 totals 照旧。"""
        store = MeterStore(tmp_path / "meter.db")
        meter = Meter(store=store)
        try:
            meter.record(_llm_rec(inp=60, out=40))
            meter.record(MeterRecord(kind="tool", name="t", ms=1.0,
                                     ts=_ts(2026, 1, 15, 12, 0)))  # tool 不落库
            assert meter.tokens_used_today(now=_ts(2026, 1, 15, 13, 0)) == 100
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 13, 0)) == 100
            assert meter.totals()["llm_calls"] == 1
            assert meter.totals()["tool_calls"] == 1
        finally:
            meter.close()

    def test_crosses_utc_midnight_by_record_ts(self, tmp_path) -> None:
        """按 rec.ts 切日落库(不是按调用时刻):昨日记录不计入今日。"""
        store = MeterStore(tmp_path / "meter.db")
        meter = Meter(store=store)
        try:
            meter.record(_llm_rec(inp=100, ts=_ts(2026, 1, 15, 23, 59)))
            assert meter.tokens_used_today(now=_ts(2026, 1, 16, 8, 0)) == 0
            assert meter.tokens_used_today(now=_ts(2026, 1, 15, 23, 59)) == 100
        finally:
            meter.close()

    def test_store_is_authoritative_no_double_count(self, tmp_path) -> None:
        """有 store 时只读 store,不叠加内存 records(否则同一条会双计)。"""
        store = MeterStore(tmp_path / "meter.db")
        meter = Meter(store=store)
        try:
            meter.record(_llm_rec(inp=30))  # 内存与 store 各有 30
            store.add("llm", 100, 0, ts=_ts(2026, 1, 15, 9, 0))  # 模拟重启前存量
            assert meter.tokens_used_today(now=_ts(2026, 1, 15, 10, 0)) == 130
        finally:
            meter.close()


class TestRestartPersistence:
    """build_agent 同 data_dir 重建(模拟重启):用量与配额拦截跨进程仍在。"""

    async def test_usage_survives_rebuild(self, tmp_path) -> None:
        data, ws = tmp_path / "rd", tmp_path / "ws"
        fake = FakeLLM(dynamic=lambda m, t: LLMReply(
            text="好", usage=Usage(input_tokens=12, output_tokens=6)
        ))
        app1 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            await app1.master._llm.complete([{"role": "user", "content": "hi"}])
            assert app1.meter.tokens_used_today() == 18
        finally:
            app1.close()
        app2 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            assert app2.meter.tokens_used_today() == 18  # 重启不归零
            quota = await execute(app2.registry, "get_resource_quota", USER_CTX, {})
            assert quota["tokens_used_today"] == 18  # capability 读同一持久化源
        finally:
            app2.close()

    async def test_quota_blocks_after_rebuild(self, tmp_path) -> None:
        """第一次进程记满配额;重建后 metered_llm 仍拒,底层 LLM 不被调。"""
        data, ws = tmp_path / "rd", tmp_path / "ws"
        fake = FakeLLM(default="好")
        app1 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            await app1.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            # ts 取真实时钟:重启后 tokens_used_today 按真实「今天」读库
            app1.meter.record(_llm_rec(inp=60, out=40, ts=time.time()))
        finally:
            app1.close()
        app2 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            await app2.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            reply = await app2.master._llm.complete([{"role": "user", "content": "hi"}])
            assert "配额" in (reply.text or "")
            assert len(fake.calls) == 0  # 底层未被调
        finally:
            app2.close()
