"""agent.cancel_run 急停闭环测试(§9.2 Parity 补全):用户与 agent 同权急停。"""

import asyncio

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

from agent.llm import FakeLLM
from agent.main import build_agent
from agent.runtime.state import RunStatus
from agent.subagent import Mode, TaskBook


def _app(tmp_path, llm=None):
    return build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws",
                       llm=llm or FakeLLM())


class TestCancelRun:
    async def test_cancel_by_name_stops_running_task(self, tmp_path) -> None:
        class HangingLLM(FakeLLM):
            """挂起在 complete 上,制造可急停的运行中窗口。"""

            async def complete(self, *args, **kw):  # noqa: ANN001, ANN002, ANN003
                await asyncio.Event().wait()

        app = _app(tmp_path, HangingLLM())
        inst = app.spawner.spawn(TaskBook(goal="长任务", mode=Mode.REACT),
                                 name="job")
        task = asyncio.create_task(app.spawner.start(inst))
        await asyncio.sleep(0.02)
        assert inst.status.alive

        out = await execute(app.registry, "cancel_run",
                            ActorContext(actor=LOCAL_USER), {"id_or_name": "job"})
        assert out["cancelled"] == [inst.id]
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert inst.state.status is RunStatus.CANCELLED

    async def test_cancel_unknown_404(self, tmp_path) -> None:
        app = _app(tmp_path)
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "cancel_run",
                          ActorContext(actor=LOCAL_USER),
                          {"id_or_name": "ghost"})
        assert exc.value.body.code == "AGENT.NOT_FOUND"
