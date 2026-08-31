"""事件流测试:日志追加/按序读/过滤;直推订阅;掉队补读;游标恢复。"""


import pytest
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import CursorStore, EventBus, EventLog

AGENT = ActorRef(kind=ActorKind.AGENT, id="agent.main")


def _ev(type_: str, **payload) -> Event:
    return Event(type=type_, actor=AGENT, payload=payload)


@pytest.fixture()
def log(tmp_path):
    lg = EventLog(tmp_path / "events.db")
    yield lg
    lg.close()


class TestEventLog:
    def test_append_assigns_increasing_seq(self, log) -> None:
        s1 = log.append(_ev("a"))
        s2 = log.append(_ev("b"))
        assert s2 > s1

    def test_read_after_with_type_filter(self, log) -> None:
        log.append(_ev("task.progress", n=1))
        log.append(_ev("agent.message", text="hi"))
        rows = log.read_after(types=["task.progress"])
        assert len(rows) == 1
        assert rows[0][1].payload == {"n": 1}

    def test_read_after_glob_types(self, log) -> None:
        """glob 与订阅同语义(phase-15):字面量 'task.*' 补读能拿到 task.progress。"""
        log.append(_ev("task.enqueued", id="t1"))
        log.append(_ev("task.progress", pct=50))
        log.append(_ev("agent.message", text="hi"))
        rows = log.read_after(types=["task.*"])
        assert [e.type for _, e in rows] == ["task.enqueued", "task.progress"]

    def test_read_after_mixed_exact_and_glob(self, log) -> None:
        """精确类型与 glob 混用:并集,按 seq 升序;不在查询集的类型不返回。"""
        log.append(_ev("agent.message", text="a"))
        log.append(_ev("task.progress", pct=1))
        log.append(_ev("user.message", text="b"))
        rows = log.read_after(types=[DomainEvent.AGENT_MESSAGE, "task.*"])
        assert [e.type for _, e in rows] == ["agent.message", "task.progress"]

    def test_roundtrip_preserves_fields(self, log) -> None:
        ev = _ev("user.message", text="你好")
        log.append(ev)
        restored = log.read_after()[0][1]
        assert restored.id == ev.id
        assert restored.actor == AGENT
        assert restored.payload == {"text": "你好"}

    def test_cross_instance_shared_db(self, tmp_path) -> None:
        """两个进程(实例)共享同一 db:一方写,另一方游标读。"""
        path = tmp_path / "events.db"
        writer = EventLog(path)
        writer.append(_ev("graph.indexed", repo="x"))
        reader = EventLog(path)
        assert [e.type for _, e in reader.read_after()] == ["graph.indexed"]
        writer.close()
        reader.close()


class TestCursorStore:
    def test_default_zero_and_roundtrip(self, log) -> None:
        cs = CursorStore(log.conn)
        assert cs.get("graph.worker") == 0
        cs.set("graph.worker", 42)
        assert cs.get("graph.worker") == 42


class TestEventBus:
    async def test_publish_pushes_to_matching_subscriber(self, log) -> None:
        bus = EventBus(log)
        sub = bus.subscribe("task.*")
        other = bus.subscribe("user.*")
        ev = _ev("task.progress", n=1)
        await bus.publish(ev)
        assert (await sub.get(timeout=1)) is ev
        assert other.queue.empty()

    async def test_event_persisted_before_push(self, log) -> None:
        bus = EventBus(log)
        await bus.publish(_ev(DomainEvent.AGENT_MESSAGE, text="hi"))
        assert bus.replay()[0][1].type == "agent.message"

    async def test_slow_subscriber_lagged_then_catches_up(self, log) -> None:
        bus = EventBus(log, queue_size=1)
        sub = bus.subscribe("*")
        await bus.publish(_ev("a"))
        await bus.publish(_ev("b"))  # 队列满,直推丢弃但已落日志
        assert sub.lagged
        missed = bus.read_missed("sub-1", CursorStore(log.conn))
        assert [e.type for _, e in missed] == ["a", "b"]

    async def test_cursor_not_advanced_when_idle(self, log) -> None:
        bus = EventBus(log)
        await bus.publish(_ev("a"))
        cs = CursorStore(log.conn)
        bus.read_missed("sub-1", cs)
        assert bus.read_missed("sub-1", cs) == []  # 已消费,不重复
        assert cs.get("sub-1") == 1

    async def test_unsubscribe(self, log) -> None:
        bus = EventBus(log)
        sub = bus.subscribe("*")
        bus.unsubscribe(sub)
        await bus.publish(_ev("a"))
        assert sub.queue.empty()
