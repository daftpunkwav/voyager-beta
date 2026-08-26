"""notes 服务测试(§8.3):CRUD、摘要/全文两级加载、关联、事件、状态机、
版本历史、双向链接、检索增强。"""

from pathlib import Path

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
    store = NoteStore(tmp_path / "notes.db", history_keep=5)
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

    async def test_delete_moves_to_trash_and_restore(self, deps) -> None:
        """软删除语义:delete → 回收站可恢复;purge 才彻底删。"""
        _, log = deps
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": "待删", "content": "正文"})
        nid = note["id"]
        await execute(registry, "delete_note", USER_CTX, {"note_id": nid})
        trashed = await execute(registry, "get_note", USER_CTX, {"note_id": nid})
        assert trashed["trashed_ts"] is not None  # 按 id 可直读回收站笔记
        await execute(registry, "restore_note", USER_CTX, {"note_id": nid})
        back = await execute(registry, "get_note", USER_CTX, {"note_id": nid})
        assert back["trashed_ts"] is None
        await execute(registry, "purge_note", USER_CTX, {"note_id": nid})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "get_note", USER_CTX, {"note_id": nid})
        assert exc.value.body.code == "NOTES.NOT_FOUND"
        types = [e.type for _, e in log.read_after()]
        for expected in ("note.created", "note.deleted", "note.restored", "note.purged"):
            assert expected in types

    async def test_delete_twice_conflict(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {"title": "x"})
        await execute(registry, "delete_note", USER_CTX, {"note_id": note["id"]})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "delete_note", USER_CTX, {"note_id": note["id"]})
        assert exc.value.body.code == "NOTES.CONFLICT"

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


class TestStatesAndSearch:
    async def test_state_views_exclude_each_other(self, deps) -> None:
        n1 = await execute(registry, "create_note", USER_CTX, {"title": "普通"})
        n2 = await execute(registry, "create_note", USER_CTX, {"title": "归档件"})
        await execute(registry, "update_note", USER_CTX,
                      {"note_id": n2["id"], "archived": True})
        await execute(registry, "delete_note", USER_CTX, {"note_id": n1["id"]})

        active = await execute(registry, "list_notes", USER_CTX, {})
        archived = await execute(registry, "list_notes", USER_CTX, {"state": "archived"})
        trash = await execute(registry, "list_notes", USER_CTX, {"state": "trash"})
        everything = await execute(registry, "list_notes", USER_CTX, {"state": "all"})
        assert active == []  # 归档与回收站都不进默认视图
        assert {n["title"] for n in archived} == {"归档件"}
        assert {n["title"] for n in trash} == {"普通"}
        assert len(everything) == 2
        assert archived[0]["archived"] is True

    async def test_query_search_escaped_wildcard(self, deps) -> None:
        await execute(registry, "create_note", USER_CTX,
                      {"title": "进度100%", "content": "不含关键词"})
        hits = await execute(registry, "list_notes", USER_CTX, {"query": "100%"})
        assert len(hits) == 1  # % 不作通配符;若未转义将误匹配
        assert await execute(registry, "list_notes", USER_CTX, {"query": "不匹配"}) == []

    async def test_pin_sorting(self, deps) -> None:
        await execute(registry, "create_note", USER_CTX, {"title": "甲"})
        second = await execute(registry, "create_note", USER_CTX, {"title": "乙"})
        await execute(registry, "update_note", USER_CTX,
                      {"note_id": second["id"], "pinned": True})
        listing = await execute(registry, "list_notes", USER_CTX, {"sort": "created"})
        assert listing[0]["pinned"] is True
        assert listing[0]["title"] == "乙"


class TestTagsEnhanced:
    async def test_list_tags_counts_excludes_trash(self, deps) -> None:
        a = await execute(registry, "create_note", USER_CTX,
                          {"title": "a", "tags": ["rust", "学习"]})
        await execute(registry, "create_note", USER_CTX,
                      {"title": "b", "tags": ["学习"]})
        await execute(registry, "delete_note", USER_CTX, {"note_id": a["id"]})
        tags = {t["tag"]: t["count"]
                for t in await execute(registry, "list_tags", USER_CTX, {})}
        assert tags == {"学习": 1}

    async def test_rename_tag_globally(self, deps) -> None:
        await execute(registry, "create_note", USER_CTX,
                      {"title": "a", "tags": ["js", "前端"]})
        b = await execute(registry, "create_note", USER_CTX,
                          {"title": "b", "tags": ["js"]})
        out = await execute(registry, "rename_tag", USER_CTX,
                            {"old": "js", "new": "typescript"})
        assert out["affected"] == 2
        tags_b = (await execute(registry, "get_note", USER_CTX,
                                {"note_id": b["id"]}))["tags"]
        assert tags_b == ["typescript"]

    async def test_stats_counts(self, deps) -> None:
        a = await execute(registry, "create_note", USER_CTX, {"title": "s1"})
        await execute(registry, "update_note", USER_CTX,
                      {"note_id": a["id"], "archived": True})
        await execute(registry, "create_note", USER_CTX, {"title": "s2"})
        stats = await execute(registry, "notes_stats", USER_CTX, {})
        assert stats["active"] == 1 and stats["archived"] == 1 and stats["total"] == 2


class TestVersions:
    async def test_content_changes_snapshot_and_restore(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": "v文", "content": "第一版"})
        nid = note["id"]
        await execute(registry, "update_note", USER_CTX,
                      {"note_id": nid, "content": "第二版"})
        await execute(registry, "update_note", USER_CTX,
                      {"note_id": nid, "content": "第二版"})  # 相同内容不再快照
        versions = (await execute(registry, "list_versions", USER_CTX,
                                  {"note_id": nid}))["versions"]
        assert [v["version"] for v in versions] == [1]
        snap = await execute(registry, "read_version", USER_CTX,
                             {"note_id": nid, "version": 1})
        assert snap["content"] == "第一版"
        restored = await execute(registry, "restore_version", USER_CTX,
                                 {"note_id": nid, "version": 1})
        assert restored["content"] == "第一版"  # 当前内容回退
        again = await execute(registry, "list_versions", USER_CTX, {"note_id": nid})
        assert again["versions"][0]["version"] == 2  # 回退本身形成新快照

    async def test_history_keep_cap(self, deps) -> None:
        store, _ = deps
        nid = store.create({"title": "freq", "content": "0"})
        for i in range(1, 10):
            store.update(nid, content=f"第{i}版")  # history_keep=5
        versions = store.list_versions(nid)
        assert [v["version"] for v in versions] == [9, 8, 7, 6, 5]


class TestBacklinks:
    async def test_link_sync_and_backlink_view(self, deps) -> None:
        target = await execute(registry, "create_note", USER_CTX,
                               {"title": "目标页", "content": "被链接的页面"})
        await execute(registry, "create_note", USER_CTX,
                      {"title": "引用页", "content": "见 [[目标页]] 与 [[不存在页]]"})
        links = (await execute(registry, "get_backlinks", USER_CTX,
                               {"note_id": target["id"]}))["backlinks"]
        assert [link["title"] for link in links] == ["引用页"]

    async def test_links_dropped_on_purge(self, deps) -> None:
        src = await execute(registry, "create_note", USER_CTX,
                            {"title": "源", "content": "指 [[的页]]"})
        dst = await execute(registry, "create_note", USER_CTX,
                            {"title": "的页"})
        await execute(registry, "purge_note", USER_CTX, {"note_id": src["id"]})
        remaining = (await execute(registry, "get_backlinks", USER_CTX,
                                   {"note_id": dst["id"]}))["backlinks"]
        assert remaining == []


class TestExportAndLinkFields:
    async def test_export_note_writes_markdown(self, deps, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)  # 导出相对路径落 tmp
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": '导出"测"/试', "content": "# 正文\n内容",
                              "tags": ["t1"]})
        out = await execute(registry, "export_note", USER_CTX, {"note_id": note["id"]})
        path = tmp_path / "workspace" / "notes-export" / Path(out["path"]).name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n") and "# 正文" in text
        assert "/" not in path.name and '"' not in path.name  # 文件名已清洗

    async def test_link_note_clears_with_empty_string(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": "n", "source_id": "src1"})
        cleared = await execute(registry, "link_note", USER_CTX,
                                {"note_id": note["id"], "source_id": ""})
        assert cleared["source_id"] == ""

    async def test_agent_parity_write(self, deps) -> None:
        """agent 同权建改笔记(铁律 4)。"""
        note = await execute(registry, "create_note", AGENT_CTX,
                             {"title": "agent 建", "content": "同权"})
        updated = await execute(registry, "update_note", AGENT_CTX,
                                {"note_id": note["id"], "pinned": True})
        assert updated["pinned"] is True


class TestMigration:
    async def test_legacy_db_upgrades_with_defaults(self, tmp_path) -> None:
        """旧 schema(无 archived/pinned/trashed_ts)打开后自动补列且数据保留。"""
        import sqlite3

        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE notes (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
                source_id TEXT NOT NULL DEFAULT '', node_id TEXT NOT NULL DEFAULT '',
                created_ts REAL NOT NULL, updated_ts REAL NOT NULL);
            INSERT INTO notes VALUES ('old1','旧笔记','内容','[]','','',1,2);
        """)
        conn.commit()
        conn.close()
        store = NoteStore(db)
        note = store.get("old1")
        assert note["title"] == "旧笔记"
        assert note["archived"] is False and note["pinned"] is False
        assert note["trashed_ts"] is None
        store.close()


class TestRetention:
    async def test_purge_expired_respects_retention(self, deps) -> None:
        """retention=0 永不清理;超期清、未期留。"""
        import time as _t

        store, _ = deps
        a = store.create({"title": "旧", "content": ""})
        b = store.create({"title": "新", "content": ""})
        store.trash(a)
        store.trash(b)
        old = _t.time() - 31 * 86400
        store._conn.execute("UPDATE notes SET trashed_ts=? WHERE id=?", (old, a))
        store._conn.commit()
        assert store.purge_expired(0) == 0          # 0 = 永久保留
        assert store.purge_expired(30) == 1         # 只清超期的 a
        assert store.get(a) is None and store.get(b) is not None
