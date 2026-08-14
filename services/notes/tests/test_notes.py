"""notes 服务测试(§8.3):CRUD、摘要/全文两级加载、关联、事件。"""

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_eventbus import EventBus, EventLog

from services.notes.capabilities import Deps, init_deps, registry
from services.notes.store import NoteStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def deps(tmp_path):
    log = EventLog(tmp_path / "events.db")
    store = NoteStore(tmp_path / "notes.db")
    init_deps(Deps(store=store, bus=EventBus(log)))
    yield store, log
    store.close()
    log.close()


class TestCrud:
    async def test_create_and_get(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": "学 langgraph", "content": "# 大纲\n要点",
                              "tags": ["agent"]})
        assert note["id"]
        full = await execute(registry, "get_note", AGENT_CTX, {"note_id": note["id"]})
        assert full["content"].startswith("# 大纲")  # agent 同权读(铁律 4)

    async def test_update_and_events(self, deps) -> None:
        _, log = deps
        note = await execute(registry, "create_note", USER_CTX, {"title": "t"})
        await execute(registry, "update_note", USER_CTX,
                      {"note_id": note["id"], "content": "新正文"})
        types = [e.type for _, e in log.read_after()]
        assert types == ["note.created", "note.edited"]

    async def test_delete_irreversible_and_missing_404(self, deps) -> None:
        _, log = deps
        note = await execute(registry, "create_note", USER_CTX, {"title": "t"})
        assert registry.get("delete_note").reversible is False
        await execute(registry, "delete_note", USER_CTX, {"note_id": note["id"]})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "get_note", USER_CTX, {"note_id": note["id"]})
        assert exc.value.body.code == "NOTES.NOT_FOUND"
        assert "note.deleted" in [e.type for _, e in log.read_after()]

    async def test_list_summary_truncates_content(self, deps) -> None:
        store, _ = deps
        store.create({"title": "长文", "content": "字" * 500})
        out = await execute(registry, "list_notes", USER_CTX, {})
        assert "content" not in out[0]  # 列表不回全文(§9.20)
        assert len(out[0]["excerpt"]) == 120

    async def test_list_filter_by_tag_and_source(self, deps) -> None:
        await execute(registry, "create_note", USER_CTX,
                      {"title": "a", "tags": ["x"], "source_id": "s1"})
        await execute(registry, "create_note", USER_CTX, {"title": "b", "tags": ["y"]})
        assert len(await execute(registry, "list_notes", USER_CTX, {"tag": "x"})) == 1
        assert len(await execute(registry, "list_notes", USER_CTX,
                                 {"source_id": "s1"})) == 1

    async def test_link_note(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {"title": "t"})
        out = await execute(registry, "link_note", AGENT_CTX,
                            {"note_id": note["id"], "node_id": "n42"})
        assert out["node_id"] == "n42"
