"""Observe 测试(§9.2):事件 → 考虑事项;默认只留痕,开关打开才自动行动。"""

import asyncio

from platform_contracts import LOCAL_USER, Event

from agent.llm import FakeLLM
from agent.main import build_agent


def _ready_event(repo: str = "langgraph") -> Event:
    return Event(type="source.ready", actor=LOCAL_USER, payload={"repo": repo})


class TestObserver:
    async def test_source_ready_considered_and_logged(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        await app.observer.handle(_ready_event())
        episodes = app.memory.episodic.recent(kind="consider")
        assert len(episodes) == 1
        assert "langgraph" in episodes[0]["summary"]
        assert episodes[0]["detail"]["source"] == "source.ready"
        assert app.spawner.instances == {}  # 默认不自动行动
        app.memory.close()

    async def test_unrelated_event_ignored(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        await app.observer.handle(
            Event(type="note.created", actor=LOCAL_USER, payload={})
        )
        assert app.memory.episodic.recent(kind="consider") == []
        app.memory.close()

    async def test_auto_index_dispatches_when_enabled(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        await app.settings.set("agent.observe.auto_index", True, LOCAL_USER)
        await app.observer.handle(_ready_event("opencode"))
        await asyncio.sleep(0.05)  # dispatch 是后台任务
        names = [i.name for i in app.spawner.instances.values()]
        assert "auto-index" in names
        app.memory.close()


class TestObserveEvent:
    """phase-12:consider 发 agent.observe 事件,Chat/悬浮窗据此显示观察行。"""

    async def test_consider_publishes_agent_observe(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        await app.observer.handle(_ready_event())
        rows = app.log.read_after(after_seq=0, types=("agent.observe",))
        assert len(rows) == 1
        _seq, ev = rows[0]
        assert "langgraph" in ev.payload["content"]
        assert ev.payload["source"] == "source.ready"
        assert ev.payload["acted"] is False  # 默认不自动行动
        app.memory.close()

    async def test_consider_marks_acted_when_auto_index(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        await app.settings.set("agent.observe.auto_index", True, LOCAL_USER)
        await app.observer.handle(_ready_event("opencode"))
        await asyncio.sleep(0.05)
        rows = app.log.read_after(after_seq=0, types=("agent.observe",))
        assert len(rows) == 1
        assert rows[0][1].payload["acted"] is True
        app.memory.close()

    async def test_unmatched_event_emits_nothing(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        await app.observer.handle(Event(type="note.created", actor=LOCAL_USER, payload={}))
        assert app.log.read_after(after_seq=0, types=("agent.observe",)) == []
        app.memory.close()
