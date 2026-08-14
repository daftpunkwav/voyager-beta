"""调度与运行状态测试(§9.1/§9.17):并发上限、定时器、checkpoint 恢复。"""

import asyncio

from agent.runtime.scheduler import Scheduler
from agent.runtime.state import CheckpointStore, RunState, RunStatus


class TestScheduler:
    async def test_concurrency_limit(self) -> None:
        scheduler = Scheduler(max_concurrent=1)
        order: list[str] = []
        gate = asyncio.Event()

        async def first() -> None:
            order.append("a-start")
            await gate.wait()
            order.append("a-end")

        async def second() -> None:
            order.append("b")

        t1 = asyncio.create_task(scheduler.run("a", first()))
        await asyncio.sleep(0)  # 让 a 先拿到信号量
        t2 = asyncio.create_task(scheduler.run("b", second()))
        await asyncio.sleep(0.01)
        assert order == ["a-start"]  # b 被信号量挡住
        assert scheduler.active() == ["a"]
        gate.set()
        await asyncio.gather(t1, t2)
        assert order == ["a-start", "a-end", "b"]
        assert scheduler.active() == []

    async def test_timer_fire_and_cancel(self) -> None:
        scheduler = Scheduler()
        fired: list[str] = []

        async def mark() -> None:
            fired.append("x")

        scheduler.call_later(0.02, mark, name="t1")
        tid = scheduler.call_later(60, mark, name="t2")
        assert scheduler.cancel_timer(tid) is True
        assert scheduler.cancel_timer("不存在") is False
        await asyncio.sleep(0.06)
        assert fired == ["x"]  # 只有 t1 触发

    async def test_cancel_named_task(self) -> None:
        scheduler = Scheduler()
        started = asyncio.Event()

        async def long() -> None:
            started.set()
            await asyncio.sleep(60)

        task = asyncio.create_task(scheduler.run("job", long()))
        await started.wait()
        assert await scheduler.cancel("job") is True
        await asyncio.sleep(0)
        assert task.cancelled()


class TestCheckpoint:
    def test_roundtrip_and_alive_filter(self, tmp_path) -> None:
        store = CheckpointStore(tmp_path)
        running = RunState(task="索引仓库")
        running.status = RunStatus.RUNNING
        running.add_step("llm", "round-1", "第 1 轮")
        store.save(running)
        done = RunState(task="整理笔记")
        done.status = RunStatus.COMPLETED
        store.save(done)

        loaded = store.load(running.run_id)
        assert loaded.task == "索引仓库"
        assert loaded.status is RunStatus.RUNNING
        assert loaded.steps[0].summary == "第 1 轮"
        alive = store.list_alive()
        assert [s.run_id for s in alive] == [running.run_id]  # 崩溃恢复只看存活
        store.delete(done.run_id)
        assert len(list(tmp_path.glob("*.json"))) == 1

    def test_status_alive_semantics(self) -> None:
        assert RunStatus.RUNNING.alive and RunStatus.WAITING_INPUT.alive
        assert not RunStatus.COMPLETED.alive and not RunStatus.FAILED.alive
