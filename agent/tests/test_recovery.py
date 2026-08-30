"""容错接线测试(phase-12 §9.17):工具重试/熔断、EventLoop pattern 熔断、checkpoint reclaim。

recovery.py 此前没有调用方;本文件锁定接线后的行为:
- 只读工具失败重试到成功;写类工具失败一次即停(防双写);
- 按工具名熔断,打开后不再进 handler;
- EventLoop 某 pattern 连续失败被跳过,其它 pattern 不受影响,loop 不炸;
- 启动 reclaim 把磁盘上 alive 的 checkpoint 标 failed(不 resume)。
"""

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


class TestToolBreaker:
    async def test_opens_after_consecutive_failures(self, tmp_path) -> None:
        """连续失败 3 次(默认 open_after)后熔断;打开后不再进 handler。"""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(10**9, counter)})
        for _ in range(3):  # 熔断按 belt.call 计次(with_retry 在其内层)
            assert "[工具失败]" in await belt.call(ToolCall("1", "flaky", {}))
        assert counter["calls"] == 9  # 3 次调用 × (1 + 2 重试)
        assert "[熔断]" in await belt.call(ToolCall("2", "flaky", {}))
        assert counter["calls"] == 9  # 打开后不再进 handler

    async def test_breaker_shared_across_trimmed_views(self, tmp_path) -> None:
        """裁剪视图与根名册同一份熔断器:不因视图重建而复位。"""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(10**9, counter)})
        for _ in range(3):
            await belt.call(ToolCall("1", "flaky", {}))
        trimmed = belt.trimmed(["flaky"])
        assert "[熔断]" in await trimmed.call(ToolCall("2", "flaky", {}))
        assert counter["calls"] == 9


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
