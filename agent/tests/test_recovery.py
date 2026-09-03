"""容错接线测试(phase-12 §9.17):工具重试/熔断、EventLoop pattern 熔断、checkpoint reclaim。

recovery.py 此前没有调用方;本文件锁定接线后的行为:
- 只读工具失败重试到成功;写类工具失败一次即停(防双写);
- 超时不重试(phase-43);按工具名熔断且按**每次 handler 尝试**计次(phase-43),
  打开后不再进 handler;
- EventLoop 某 pattern 连续失败被跳过,其它 pattern 不受影响,loop 不炸;
- 启动时无 resume 快照的 alive checkpoint 标 failed;带快照的转 PAUSED 待恢复(phase-69)。
"""

import asyncio
import contextlib
import os
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from platform_contracts import LOCAL_USER, Event
from platform_eventbus import CursorStore, EventBus, EventLog
from platform_settings import SettingsStore

from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent
from agent.memory import EpisodicMemory
from agent.policy import FsPolicy, PolicyEngine
from agent.runtime import EventLoop
from agent.runtime.state import (
    CheckpointStore,
    ResumeSnapshot,
    RunState,
    RunStatus,
    reclaim_alive,
)
from agent.settings import DEFS as AGENT_SETTING_DEFS
from agent.subagent.instance import TaskBook
from agent.subagent.spawn import TERMINAL_INSTANCE_CAP
from agent.tools import AgentTool, Toolbelt, ensure_workdir


def _flaky_tool(fails: int, counter: dict, *, write: bool = False) -> AgentTool:
    """前 fails 次调用抛错,之后成功;dimension=none 走 policy L0 放行。"""

    async def handler(**kwargs) -> str:
        counter["calls"] += 1
        if counter["calls"] <= fails:
            raise RuntimeError("boom")
        return "ok"

    return AgentTool(
        name="flaky", description="测试用易失败工具", handler=handler,
        dimension="none", write=write,
    )


def _belt(root, tools: dict[str, AgentTool]) -> Toolbelt:
    # backoff=0:单测不真睡(0.1s×n)
    return Toolbelt(
        tools, PolicyEngine(fs=FsPolicy(roots=(str(root),))), retry_backoff=0
    )


class TestToolRetry:
    async def test_read_only_tool_retries_then_succeeds(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(2, counter)})
        out = await belt.call(ToolCall("1", "flaky", {}))
        assert out == "ok"
        assert counter["calls"] == 3  # 首次 + 2 次重试

    async def test_write_tool_never_retries(self, tmp_path) -> None:
        """写类工具失败一次即停:重试会双写/重复删除。"""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(1, counter, write=True)})
        out = await belt.call(ToolCall("1", "flaky", {}))
        assert "[工具失败]" in out
        assert counter["calls"] == 1

    async def test_timeout_not_retried(self, tmp_path) -> None:
        """超时默认不重试(phase-43):MCP/shell 超时 × 退避重试只会拖长,
        只读工具抛 TimeoutError 也只进 1 次 handler,一次超时即失败。"""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}

        async def slow(**kwargs) -> str:
            counter["calls"] += 1
            raise TimeoutError("上游 30s 未响应")

        belt = _belt(root, {"slow": AgentTool(
            name="slow", description="测试用超时工具", handler=slow, dimension="none",
        )})
        out = await belt.call(ToolCall("1", "slow", {}))
        assert "[工具失败]" in out and "TimeoutError" in out
        assert counter["calls"] == 1

    async def test_httpx_timeout_not_retried(self, tmp_path) -> None:
        """URL 型 MCP 超时不重试(phase-46):session.py 的 httpx.AsyncClient
        超时抛 httpx.TimeoutException,与 stdio MCP(内建 TimeoutError)一致,
        只进 1 次 handler,一次失败即交熔断/[工具失败] 文本。"""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}

        async def slow(**kwargs) -> str:
            counter["calls"] += 1
            raise httpx.TimeoutException("timed out")

        belt = _belt(root, {"slow": AgentTool(
            name="slow", description="测试用 URL MCP 超时工具", handler=slow, dimension="none",
        )})
        out = await belt.call(ToolCall("1", "slow", {}))
        assert "[工具失败]" in out and "TimeoutException" in out
        assert counter["calls"] == 1

    async def test_spawn_subagent_is_write_never_retried(self, tmp_path) -> None:
        """spawn_subagent 有副作用(创建运行实例):标 write,失败只进 1 次
        handler,不按只读重试双开实例(phase-13)。"""
        from agent.tools.spawn_subagent import spawn_tool

        calls = {"n": 0}

        async def failing_dispatch(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("boom")

        tool = spawn_tool(failing_dispatch)["spawn_subagent"]
        assert tool.write is True
        root = ensure_workdir(tmp_path / "ws")
        belt = _belt(root, {"spawn_subagent": tool})
        out = await belt.call(ToolCall("t1", "spawn_subagent", {"goal": "x"}))
        assert "[工具失败]" in out
        assert calls["n"] == 1


class TestToolBreaker:
    async def test_opens_after_consecutive_failures(self, tmp_path) -> None:
        """连续 3 次 handler 失败(默认 open_after)即熔断;重试内每次尝试都计数,
        不再按外层 belt.call 计 1 次(旧结构 3×3=9 次才断,phase-43)。"""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(10**9, counter)})
        # 单次 belt.call 内 3 次 handler 尝试全部失败 → 熔断立即打开
        assert "[工具失败]" in await belt.call(ToolCall("1", "flaky", {}))
        assert counter["calls"] == 3
        assert "[熔断]" in await belt.call(ToolCall("2", "flaky", {}))  # 后续直接熔断
        assert counter["calls"] == 3  # 打开后不再进 handler

    async def test_breaker_shared_across_trimmed_views(self, tmp_path) -> None:
        """裁剪视图与根名册同一份熔断器:不因视图重建而复位。"""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(10**9, counter)})
        await belt.call(ToolCall("1", "flaky", {}))  # 3 次 handler 失败,熔断打开
        trimmed = belt.trimmed(["flaky"])
        assert "[熔断]" in await trimmed.call(ToolCall("2", "flaky", {}))
        assert counter["calls"] == 3


def _event(type_: str) -> Event:
    return Event(type=type_, actor=LOCAL_USER, payload={})


@contextlib.asynccontextmanager
async def _running_loop(loop: EventLoop):
    """起 loop.run() 任务,结束时 cancel(loop.stop 不唤醒 sub.get,需 cancel 收尾)。

    等 run 真正进入直推 while(run() 先做同步补读、再 subscribe、再进 while;
    create_task + 单次 sleep(0) 只跑到第一个 await 即让出,不能保证已装配)。
    """
    task = asyncio.create_task(loop.run())
    for _ in range(100):  # 轮询 _sub 装配(纯内存,毫秒级就位)
        if loop._sub is not None:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("loop.run() 未装配运行期订阅(sub 仍为 None)")
    await asyncio.sleep(0)  # 确保 run 已从 read_missed 返回并阻塞在 sub.get
    try:
        yield
    finally:
        loop.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class TestLoopBreaker:
    async def test_consecutive_failures_skip_handler(self, tmp_path) -> None:
        """同一 handler 连续抛错 3 次后熔断,第 4 个事件不再进入;loop 不炸。"""
        log = EventLog(tmp_path / "events.db")
        calls = {"bad": 0, "good": 0}

        async def bad(_ev: Event) -> None:
            calls["bad"] += 1
            raise RuntimeError("boom")

        async def good(_ev: Event) -> None:
            calls["good"] += 1

        loop = EventLoop(EventBus(log), {"bad.*": bad, "good.*": good})
        for _ in range(3):
            await loop._dispatch(_event("bad.x"))
        assert calls["bad"] == 3
        await loop._dispatch(_event("bad.x"))  # 熔断中:跳过,不再进入
        assert calls["bad"] == 3
        await loop._dispatch(_event("good.y"))  # 其它 pattern 不受影响
        assert calls["good"] == 1
        log.close()


class TestLoopSubscribe:
    """精确订阅(phase-28):禁 "*",hook 走 relay,订阅 = handlers + extra_patterns。"""

    async def test_star_in_handlers_rejected(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        with pytest.raises(ValueError, match="relay"):
            EventLoop(EventBus(log), {"*": noop})
        log.close()

    async def test_star_in_extra_patterns_rejected(self, tmp_path) -> None:
        """extra_patterns 里的 "*" 一样拒绝:否则精确订阅被偷懒抵消;note.* 允许。"""
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=("note.*",))
        assert "note.*" in loop.patterns  # 通配类型放行
        with pytest.raises(ValueError, match="relay"):
            EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=("*",))
        log.close()

    async def test_patterns_dedup_preserve_order(self, tmp_path) -> None:
        """订阅 pattern 去重保序:handlers keys 在前,extra_patterns 补充在后。"""
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(
            EventBus(log),
            {"bad.*": noop, "good.*": noop},
            extra_patterns=("note.created", "bad.*", "note.created"),
        )
        assert loop.patterns == ("bad.*", "good.*", "note.created")
        log.close()

    async def test_relay_breaker_does_not_touch_domain_handler(self, tmp_path) -> None:
        """relay 连续失败熔断后只 skip relay,领域 handler 照常;loop 不炸。"""
        log = EventLog(tmp_path / "events.db")
        calls = {"good": 0, "relay": 0}

        async def good(_ev: Event) -> None:
            calls["good"] += 1

        async def bad_relay(_ev: Event) -> None:
            calls["relay"] += 1
            raise RuntimeError("relay boom")

        loop = EventLoop(EventBus(log), {"good.*": good}, relay=bad_relay)
        for _ in range(5):  # 前 3 次进 relay,之后熔断跳过;handler 每次都跑
            await loop._dispatch(_event("good.x"))
        assert calls["good"] == 5
        assert calls["relay"] == 3  # open_after 默认 3,熔断后不再进入
        log.close()


class TestLoopDynamicSubscribe:
    """phase-75:运行期 hook 事件订阅动态增删(批准即订 / 撤销即退,免重启)。

    方案 R1:EventLoop 自持运行期 Subscription,`sync_extra_patterns` 幂等收敛
    到 handlers + extra;无换订间隙、无双订。handlers 领域绑定恒不可撤。
    """

    async def test_sync_adds_extra_pattern_and_keeps_handlers(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=())
        assert loop.patterns == ("user.message",)
        loop.sync_extra_patterns(("note.created",))
        assert loop.patterns == ("user.message", "note.created")

    async def test_sync_removes_only_extra_handlers_untouchable(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=("note.created",))
        loop.sync_extra_patterns(())  # 撤全部 extra
        assert loop.patterns == ("user.message",)  # 领域绑定不可撤
        log.close()

    async def test_sync_rejects_star(self, tmp_path) -> None:
        """动态 API 与构造同禁令:pattern 出现 "*" 一律拒绝(phase-28 保留)。"""
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop})
        with pytest.raises(ValueError, match="relay"):
            loop.sync_extra_patterns(("*",))
        log.close()

    async def test_run_started_sync_updates_live_sub(self, tmp_path) -> None:
        """已启动后 sync 直接改运行期 sub:未来发布的新 pattern 事件即达,不换订。"""
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []

        async def noop(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(bus, {"user.message": noop}, relay=noop)
        async with _running_loop(loop):
            assert loop._sub is not None and loop.patterns == ("user.message",)
            loop.sync_extra_patterns(("note.created",))
            await bus.publish(_event("note.created"))  # 新 pattern:直推应达
            await asyncio.sleep(0)
            assert seen == ["note.created"]  # hook 领域事件经 relay 可见
            assert loop.patterns == ("user.message", "note.created")

    async def test_run_started_drop_stops_new_events(self, tmp_path) -> None:
        """已启动后撤订:再发布该类型不再直推(注册已卸 + 订阅 pattern 已退)。"""
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []

        async def noop(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(bus, {"user.message": noop}, extra_patterns=("note.created",))
        async with _running_loop(loop):
            loop.sync_extra_patterns(())
            await bus.publish(_event("note.created"))
            await bus.publish(_event("user.message"))
            await asyncio.sleep(0)
            assert seen == ["user.message"]  # 已撤的 note.created 不进 loop

    async def test_sync_before_run_affects_boot_subscription(self, tmp_path) -> None:
        """未启动时 sync 只更新快照,run() 按最新 patterns 订阅(补读与直推一致)。"""
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []

        async def noop(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(
            bus, {"user.message": noop},
            cursors=CursorStore(log.conn), relay=noop,
        )
        # 先落一条 note.created:未 run 时它在游标之后,启动补读应按最新订阅读到
        await bus.publish(_event("note.created"))
        loop.sync_extra_patterns(("note.created",))  # run 前动态增订
        async with _running_loop(loop):
            await asyncio.sleep(0)
            assert seen == ["note.created"]  # 补读 types=最新快照,含动态新增(经 relay)

    async def test_extra_patterns_snapshot_backfill_disclosed(self, tmp_path) -> None:
        """披露:补读 types 取启动快照;run 已启动后动态新增的 pattern 只走直推。

        单测断言限制:进程内同事件循环可夹出直推子集,但进程内事件不可能
        「落日志于 run 启动之后、sync 新增之前、且直推因尚未订阅而漏掉」——
        直推与订阅在同一事件循环同步段判定,不存在该竞态窗口(见写回 E3)。
        此处验证:同类型事件在动态撤订前后发布,不双处理、撤订后不达;
        sync 撤订前的已订事件仍经 relay 恰一次(直推一次、relay 一次)。
        """
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []
        # relay 兼当观察者(与 loop 实际装配形态一致:领域事件走 relay→on_event)
        async def on_activity(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(
            bus, {"user.activity": on_activity},
            cursors=CursorStore(log.conn),
            relay=on_activity,
        )
        loop.sync_extra_patterns(("note.created",))  # run 前先订阅(模拟启动时已批准)
        async with _running_loop(loop):
            # 事件1:已订阅的 note.created → 直推 + relay(无领域 handler)
            await bus.publish(_event("note.created"))
            # 事件2:动态撤掉 note.created 后发布 → 不进 loop(已退订)
            loop.sync_extra_patterns(())
            await bus.publish(_event("note.created"))
            # 事件3:user.activity(领域 handler,不受动态影响)→ 直推 + relay
            await bus.publish(_event("user.activity"))
            await asyncio.sleep(0)
            # 事件1 经 relay 1 次;事件2 不进;事件3 relay + 领域 handler 各 1 次
            assert seen == ["note.created", "user.activity", "user.activity"]


class TestReclaim:
    def test_reclaim_marks_running_failed(self, tmp_path) -> None:
        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="t")
        state.status = RunStatus.RUNNING
        store.save(state)

        out = reclaim_alive(store)

        assert len(out) == 1
        assert store.list_alive() == []
        loaded = store.load(state.run_id)
        assert loaded.status is RunStatus.FAILED
        assert loaded.error == "进程重启,任务未恢复"

    def test_reclaim_noop_on_empty_store(self, tmp_path) -> None:
        assert reclaim_alive(CheckpointStore(tmp_path / "cp")) == []

    async def test_build_agent_reclaims_on_boot(self, tmp_path) -> None:
        """build_agent(启动装配)phase-69 语义:无 resume 的 legacy alive → FAILED;
        带 resume 快照的 alive → PAUSED 待恢复,仍在 list_alive。"""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        store = CheckpointStore(cp_dir)
        legacy = RunState(task="t")
        legacy.status = RunStatus.RUNNING
        legacy.run_id = "legacy000001"
        store.save(legacy)
        snap = ResumeSnapshot(
            instance_id="inst0001", instance_name="侦察", persona="recon", goal="索引仓库",
            history=[{"role": "user", "content": "开始"}],
        )
        resumable = RunState(
            task=snap.goal, run_id="resume00001", status=RunStatus.RUNNING,
            resume=snap.to_dict(),
        )
        store.save(resumable)

        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            loaded = store.load(legacy.run_id)
            assert loaded.status is RunStatus.FAILED
            assert loaded.error == "进程重启,任务未恢复"
            kept = store.load(resumable.run_id)
            assert kept.status is RunStatus.PAUSED
            assert kept.error == "进程重启,可恢复"
            assert {s.run_id for s in store.list_alive()} == {resumable.run_id}
        finally:
            app.memory.close()

    def test_build_agent_skips_broken_checkpoint(self, tmp_path) -> None:
        """checkpoint 目录混有坏 JSON 时启动装配不炸;合法 alive 照旧标 failed,坏文件保留。"""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        (cp_dir / "broken.json").write_text("{not json", encoding="utf-8")
        store = CheckpointStore(cp_dir)
        state = RunState(task="t")
        state.status = RunStatus.RUNNING
        store.save(state)

        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            assert store.list_alive() == []
            loaded = store.load(state.run_id)
            assert loaded.status is RunStatus.FAILED
            # 坏文件原样保留:不 unlink、不改写
            assert (cp_dir / "broken.json").read_text(encoding="utf-8") == "{not json"
        finally:
            app.memory.close()


class TestCheckpointAtomicWrites:
    """原子写(phase-73 §9.17 A):save 走 tmp + os.replace,读方永远见整文件。"""

    def test_save_is_atomic_and_no_tmp_left(self, tmp_path) -> None:
        """save 后目标合法 JSON,目录里不留 .tmp 孤儿文件。"""
        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="原子写", status=RunStatus.RUNNING)
        state.add_step("llm", "round-1", "第 1 轮")

        store.save(state)

        loaded = store.load(state.run_id)
        assert loaded.task == "原子写"
        assert loaded.status is RunStatus.RUNNING
        assert len(loaded.steps) == 1
        leftovers = [p.name for p in (tmp_path / "cp").glob("*.tmp")]
        assert leftovers == []

    def test_save_does_not_truncate_existing_target(self, tmp_path, monkeypatch) -> None:
        """目标已存在时,replace 成功前旧文件保持完整:半写窗口只限 tmp
        (monkeypatch 让首次 replace 失败,save 抛错且旧 JSON 仍可读,
        同 run 再 save 后覆盖成功)。"""
        import agent.runtime.state as state_mod

        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="v1", status=RunStatus.RUNNING)
        state.run_id = "atomicsave01"
        store.save(state)

        real_replace = os.replace
        failed = {"n": 0}

        def _flaky_replace(src, dst):
            if failed["n"] == 0 and str(dst).endswith("atomicsave01.json"):
                failed["n"] += 1
                raise OSError("模拟 replace 失败")
            return real_replace(src, dst)

        monkeypatch.setattr(state_mod.os, "replace", _flaky_replace)
        state.task = "v2"
        with pytest.raises(OSError):  # replace 失败 → save 抛错,调用方可见
            store.save(state)

        loaded = store.load(state.run_id)
        assert loaded.task == "v1"  # 旧整文件未被截断

        monkeypatch.setattr(state_mod.os, "replace", real_replace)
        store.save(state)  # 重试成功
        assert store.load(state.run_id).task == "v2"

    def test_concurrent_saves_then_load_valid(self, tmp_path) -> None:
        """同一 run 并发连续 save:目标文件永远是某次完整写入(load 不炸),
        即使 Windows 上并发 os.replace 偶发竞争失败,也不产生半写目标。"""
        from concurrent.futures import ThreadPoolExecutor

        store = CheckpointStore(tmp_path / "cp")
        store.save(RunState(task="v0", status=RunStatus.RUNNING, run_id="concurrent1"))

        def _save(i: int) -> None:
            for _ in range(5):
                st = RunState(task=f"v{i}", status=RunStatus.RUNNING)
                st.run_id = "concurrent1"
                try:
                    store.save(st)
                except OSError:
                    # Windows 并发 replace 竞争可抛 PermissionError:
                    # 单线程生产不触发;并发下个别 save 失败不等于文件半写
                    pass

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_save, range(50)))

        loaded = store.load("concurrent1")  # 不抛 JSONDecodeError
        assert loaded.status is RunStatus.RUNNING
        assert loaded.task.startswith("v")
        # 目录里只有一份目标文件;残留 .tmp 不影响 list_alive(只 glob *.json)
        assert [p.name for p in (tmp_path / "cp").glob("*.json")] == ["concurrent1.json"]
        assert {s.run_id for s in store.list_alive()} == {"concurrent1"}


class TestCheckpointTmpPurge:
    """.tmp 孤儿启动清扫(phase-76,§9.17 D):只清 save 命名形状,一层目录。"""

    def test_purge_tmp_removes_only_orphan_tmp(self, tmp_path) -> None:
        """删 `.{run_id}.json.{hex}.tmp` 形状;合法 json、无关 .tmp、子目录不动。"""
        cp = tmp_path / "cp"
        store = CheckpointStore(cp)
        state = RunState(task="t", status=RunStatus.PAUSED)
        store.save(state)  # 原子写落位,无残留
        (cp / f".{state.run_id}.json.deadbeef.tmp").write_text("残留1", encoding="utf-8")
        (cp / ".abc123.json.cafe1234.tmp").write_text("残留2", encoding="utf-8")
        (cp / "foo.tmp").write_text("非 save 形状", encoding="utf-8")
        (cp / "broken.json").write_text("{bad", encoding="utf-8")
        sub = cp / "sub"
        sub.mkdir()
        (sub / ".x.json.aaaabbbb.tmp").write_text("子目录不清", encoding="utf-8")

        removed = store.purge_tmp()

        assert removed == 2
        assert (cp / f"{state.run_id}.json").is_file()  # 合法 checkpoint 不动
        assert (cp / "broken.json").is_file()  # 坏 json 也不动(D2)
        assert (cp / "foo.tmp").is_file()  # 非 save 形状不删
        assert (sub / ".x.json.aaaabbbb.tmp").is_file()  # 不递归(D2)
        assert list(cp.glob(".*.json.*.tmp")) == []

    def test_purge_tmp_noop_on_empty_store(self, tmp_path) -> None:
        assert CheckpointStore(tmp_path / "cp").purge_tmp() == 0

    async def test_build_agent_purges_tmp_on_boot(self, tmp_path) -> None:
        """D3:build_agent 装配时清一次孤儿 .tmp,不挡启动。"""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        (cp_dir / ".orphan000001.json.deadbeef.tmp").write_text("{}", encoding="utf-8")

        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            assert list(cp_dir.glob(".*.json.*.tmp")) == []
        finally:
            app.memory.close()


class TestTerminalInstanceCap:
    """spawner 终态实例驻留上限(phase-76,§9.17 E):只淘汰终态,alive/PENDING 不动。"""

    @staticmethod
    def _spawn_many(app, n: int, *, status: RunStatus) -> list:
        insts = []
        for i in range(n):
            inst = app.spawner.spawn(TaskBook(goal=f"任务{i}"))
            inst.state.status = status
            insts.append(inst)
        return insts

    def test_trim_evicts_oldest_terminal_keeps_alive(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            alive = self._spawn_many(app, 2, status=RunStatus.RUNNING)
            terminal = self._spawn_many(
                app, TERMINAL_INSTANCE_CAP + 2, status=RunStatus.COMPLETED
            )
            evicted = app.spawner._trim_terminal_instances()
            assert evicted == [i.id for i in terminal[:2]]  # 插入序淘汰最旧(E1)
            assert len(app.spawner.instances) == TERMINAL_INSTANCE_CAP + len(alive)
            assert all(i.id in app.spawner.instances for i in alive)  # alive 不淘汰
            assert terminal[-1].id in app.spawner.instances  # 最新终态保留
        finally:
            app.memory.close()

    def test_trim_never_touches_pending_or_alive(self, tmp_path) -> None:
        """PENDING 是调度队列里还没跑的实例,不算终态(E1 不变量)。"""
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            self._spawn_many(app, 40, status=RunStatus.PENDING)
            alive = self._spawn_many(app, 5, status=RunStatus.WAITING_INPUT)
            assert app.spawner._trim_terminal_instances() == []
            assert len(app.spawner.instances) == 45
            assert all(i.id in app.spawner.instances for i in alive)
        finally:
            app.memory.close()

    async def test_cancel_triggers_trim(self, tmp_path) -> None:
        """E2 触发点:cancel 急停落 CANCELLED 后超限即淘汰最旧终态。"""
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            terminal = self._spawn_many(app, TERMINAL_INSTANCE_CAP, status=RunStatus.COMPLETED)
            (stop,) = self._spawn_many(app, 1, status=RunStatus.RUNNING)
            cancelled = await app.spawner.cancel(stop.id)
            assert cancelled == [stop.id]
            # 终态 33 > 32:最旧的 1 个被淘汰
            assert len(app.spawner.instances) == TERMINAL_INSTANCE_CAP
            assert terminal[0].id not in app.spawner.instances
            assert terminal[-1].id in app.spawner.instances
        finally:
            app.memory.close()


class TestBootEpisodicPurge:
    """启动按 retention 清理超期情节(phase-44,§9.11):不依赖用户先打开设置页。"""

    @staticmethod
    def _seed(rd: Path, *, expired: bool) -> None:
        """预写两条情节;expired=True 时把第一条 ts 拨到 365 天前。"""
        db = rd / "memory" / "episodic.db"
        epi = EpisodicMemory(db)
        epi.log("consider", "很久以前的事")
        epi.log("consider", "刚刚发生的事")
        if expired:
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "UPDATE episodes SET ts = ? WHERE summary = ?",
                    (time.time() - 365 * 86400, "很久以前的事"),
                )
                conn.commit()
            finally:
                conn.close()
        epi.close()

    async def _preset_retention(self, rd: Path, days: int) -> None:
        """build 前预写 retention(与 build_agent 同库、同注册路径)。"""
        store = SettingsStore(rd / "settings.db")
        store.register_fresh(AGENT_SETTING_DEFS)
        await store.set("agent.memory.retention_days", days, LOCAL_USER)
        store.close()

    async def test_boot_purges_expired_episodes(self, tmp_path) -> None:
        """retention>0:build_agent 装配时清掉超期情节,保留新鲜条目。"""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 30)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "很久以前的事" not in summaries
            assert "刚刚发生的事" in summaries
        finally:
            app.memory.close()

    async def test_boot_purge_zero_retention_is_noop(self, tmp_path) -> None:
        """retention=0 = 交 agent 管理:启动不清理,超期条目保留。"""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 0)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "很久以前的事" in summaries
            assert "刚刚发生的事" in summaries
        finally:
            app.memory.close()
