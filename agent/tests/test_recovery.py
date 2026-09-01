"""容错接线测试(phase-12 §9.17):工具重试/熔断、EventLoop pattern 熔断、checkpoint reclaim。

recovery.py 此前没有调用方;本文件锁定接线后的行为:
- 只读工具失败重试到成功;写类工具失败一次即停(防双写);
- 超时不重试(phase-43);按工具名熔断且按**每次 handler 尝试**计次(phase-43),
  打开后不再进 handler;
- EventLoop 某 pattern 连续失败被跳过,其它 pattern 不受影响,loop 不炸;
- 启动 reclaim 把磁盘上 alive 的 checkpoint 标 failed(不 resume)。
"""

import asyncio

import pytest
from platform_contracts import LOCAL_USER, Event
from platform_eventbus import EventBus, EventLog

from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent
from agent.policy import FsPolicy, PolicyEngine
from agent.runtime import EventLoop
from agent.runtime.state import CheckpointStore, RunState, RunStatus, reclaim_alive
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
            raise asyncio.TimeoutError("上游 30s 未响应")

        belt = _belt(root, {"slow": AgentTool(
            name="slow", description="测试用超时工具", handler=slow, dimension="none",
        )})
        out = await belt.call(ToolCall("1", "slow", {}))
        assert "[工具失败]" in out and "TimeoutError" in out
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
        """上次进程遗留的 RUNNING checkpoint 在 build_agent(启动装配)时被标 failed。"""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
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
