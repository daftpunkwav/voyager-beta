"""调度与运行状态测试(§9.1/§9.17):并发上限、定时器、checkpoint 恢复。"""

import asyncio

import pytest

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

    def test_run_id_traversal_rejected(self, tmp_path) -> None:
        """run_id 直接拼路径:../../ 之类必须被拒绝,不得穿越出 checkpoints 目录。"""
        store = CheckpointStore(tmp_path / "checkpoints")
        for bad in ("../../etc/passwd", "a/b", "..", ""):
            with pytest.raises(ValueError, match="非法 run_id"):
                store.load(bad)
            with pytest.raises(ValueError, match="非法 run_id"):
                store.delete(bad)

    def test_list_alive_skips_broken_files(self, tmp_path) -> None:
        """单份坏 checkpoint(坏 JSON / 缺字段)跳过,不挡后面的合法文件,也不删坏文件。"""
        store = CheckpointStore(tmp_path)
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        running = RunState(task="索引仓库")
        running.status = RunStatus.RUNNING
        running.run_id = "mid-run"  # 固定名保证扫描顺序:坏(b)在前、合法(m)居中、缺字段(z)殿后
        store.save(running)
        (tmp_path / "zzz-no-status.json").write_text('{"task":"x"}', encoding="utf-8")

        alive = store.list_alive()  # 混有坏文件也不抛

        assert [s.run_id for s in alive] == ["mid-run"]
        # 坏文件原样保留:不 unlink、不改写
        assert (tmp_path / "broken.json").read_text(encoding="utf-8") == "{not json"
        assert (tmp_path / "zzz-no-status.json").read_text(encoding="utf-8") == '{"task":"x"}'
