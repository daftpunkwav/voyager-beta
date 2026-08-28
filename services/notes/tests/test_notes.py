"""notes 服务测试(§8.3):CRUD、摘要/全文两级加载、关联、事件、状态机、
版本历史、双向链接、检索增强。"""

from pathlib import Path

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

from services.notes.capabilities import Deps, init_deps, registry
from services.notes.settings import DEFS
from services.notes.store import NoteStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def deps(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    store = NoteStore(tmp_path / "notes.db", history_keep=5)
    settings = SettingsStore(tmp_path / "settings.db", bus)
    settings.register_fresh(DEFS)
    init_deps(Deps(store=store, bus=bus, settings=settings, workspace=tmp_path))
    yield store, log
    store.close()
    log.close()
    settings.close()


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
    async def test_export_note_writes_markdown(self, deps, tmp_path) -> None:
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


class TestNotesView:
    async def test_get_defaults(self, deps) -> None:
        view = await execute(registry, "get_notes_view", USER_CTX, {})
        assert view["font_size"] == 15
        assert view["mode"] == "edit"
        assert view["layout"] == "list"
        assert view["sync_scroll"] is True
        assert view["list_state"] == "active"
        assert view["persisted"] is True

    async def test_user_and_agent_same_write(self, deps) -> None:
        """用户点「预览 / A+」与 agent 调 set_notes_view 落同一设置(铁律 4)。"""
        _, log = deps
        user = await execute(registry, "set_notes_view", USER_CTX,
                             {"mode": "preview", "font_delta": 2})
        assert user["mode"] == "preview"
        assert user["font_size"] == 17
        agent = await execute(registry, "set_notes_view", AGENT_CTX,
                              {"mode": "edit", "font_size": 13})
        assert agent["mode"] == "edit" and agent["font_size"] == 13
        stored = await execute(registry, "get_notes_view", AGENT_CTX, {})
        assert stored["mode"] == "edit" and stored["font_size"] == 13
        types = [e.type for _, e in log.read_after()]
        assert types.count("notes.ui.changed") >= 2

    async def test_ui_event_only_carries_changed_fields(self, deps) -> None:
        _, log = deps
        await execute(registry, "set_notes_view", USER_CTX, {"mode": "split"})
        events = [e for _, e in log.read_after() if e.type == "notes.ui.changed"]
        payload = events[-1].payload
        assert payload["mode"] == "split"
        assert "font_size" not in payload

    async def test_open_note_and_index(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {"title": "开"})
        opened = await execute(registry, "set_notes_view", AGENT_CTX,
                               {"note_id": note["id"], "mode": "preview"})
        assert opened["action"] == "open" and opened["note_id"] == note["id"]
        back = await execute(registry, "set_notes_view", USER_CTX, {"index": True})
        assert back["action"] == "index" and back["note_id"] is None

    async def test_rejects_bad_mode(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "set_notes_view", USER_CTX, {"mode": "zen"})
        assert exc.value.body.code == "NOTES.INVALID_INPUT"

    async def test_font_delta_clamps(self, deps) -> None:
        await execute(registry, "set_notes_view", USER_CTX, {"font_size": 20})
        out = await execute(registry, "set_notes_view", AGENT_CTX,
                            {"font_delta": 5})
        assert out["font_size"] == 20


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


class TestRenderAndEditSupport:
    async def test_toc_extracts_headings_skip_fence(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {
            "title": "大纲",
            "content": "# 一级\n正文\n## 二级\n```py\n# 不是标题\n```\n### 三级",
        })
        toc = (await execute(registry, "get_note_toc", USER_CTX,
                             {"note_id": note["id"]}))["toc"]
        assert [(t["level"], t["text"]) for t in toc] == [
            (1, "一级"), (2, "二级"), (3, "三级")]
        assert toc[0]["line"] == 1 and toc[1]["line"] == 3

    async def test_resolve_links_detail_with_dangling(self, deps) -> None:
        target = await execute(registry, "create_note", USER_CTX,
                               {"title": "存在页", "content": ""})
        src = await execute(registry, "create_note", USER_CTX, {
            "title": "源", "content": "[[存在页]] 与 [[幽灵页]]"})
        out = await execute(registry, "resolve_links", USER_CTX,
                            {"note_id": src["id"]})
        by_raw = {i["raw"]: i for i in out["links"]}
        assert by_raw["存在页"]["target_id"] == target["id"]
        assert by_raw["幽灵页"]["target_id"] is None
        assert out["resolved"] == 1 and out["unresolved"] == 1

    async def test_wiki_link_no_crossline_capture(self, deps) -> None:
        """[[ 不跨行:[[跨\n行]] 不得把两行拼成一个链接目标。"""
        src = await execute(registry, "create_note", USER_CTX, {
            "title": "跨行源", "content": "[[跨\n行]]"})
        out = await execute(registry, "resolve_links", USER_CTX,
                            {"note_id": src["id"]})
        assert all(i["raw"] != "跨\n行" for i in out["links"])

    async def test_edit_note_range_bold_selection(self, deps) -> None:
        """选区原子编辑:选中文字加粗场景——前端工具栏的底层动作。"""
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": "选区", "content": "这是要加粗的文字结尾"})
        start = note["content"].index("要加粗")
        end = start + len("要加粗")
        updated = await execute(registry, "edit_note_range", USER_CTX,
                                {"note_id": note["id"], "start": start,
                                 "end": end, "new_text": "**要加粗**"})
        assert updated["content"] == "这是**要加粗**的文字结尾"
        versions = (await execute(registry, "list_versions", USER_CTX,
                                  {"note_id": note["id"]}))["versions"]
        assert len(versions) == 1  # 区段编辑同样进入版本历史

    async def test_edit_note_range_out_of_bounds(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {"title": "边界", "content": "abc"})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "edit_note_range", USER_CTX,
                          {"note_id": note["id"], "start": 0, "end": 99,
                           "new_text": "x"})
        assert exc.value.body.code == "NOTES.INVALID_INPUT"

    async def test_import_note_front_matter(self, deps, tmp_path) -> None:
        f = tmp_path / "in.md"
        f.write_text("---\ntitle: 导入题\ntags: [a, b]\n---\n# 正文\n表格\n",
                     encoding="utf-8")
        imported = await execute(registry, "import_note", USER_CTX,
                                 {"file_path": str(f)})
        assert imported["title"] == "导入题"
        assert imported["tags"] == ["a", "b"]
        assert imported["content"].startswith("# 正文")
        # 显式参数覆盖 front-matter 标题
        retitled = await execute(registry, "import_note", USER_CTX,
                                 {"file_path": str(f), "title": "覆盖题"})
        assert retitled["title"] == "覆盖题"

    async def test_import_note_rejects_outside_workspace(self, deps, tmp_path) -> None:
        outsider = tmp_path.parent / f"{tmp_path.name}-outside.md"
        outsider.write_text("# secret\n", encoding="utf-8")
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "import_note", USER_CTX,
                          {"file_path": str(outsider)})
        assert exc.value.body.code == "NOTES.FORBIDDEN"

    async def test_import_note_outside_missing_is_forbidden(self, deps, tmp_path) -> None:
        """jail 外缺失文件也走 FORBIDDEN,不透露路径是否存在。"""
        ghost = tmp_path.parent / f"{tmp_path.name}-ghost.md"
        assert not ghost.exists()
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "import_note", USER_CTX,
                          {"file_path": str(ghost)})
        assert exc.value.body.code == "NOTES.FORBIDDEN"

    async def test_crlf_normalized_on_write(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX,
                             {"title": "换行", "content": "行一\r\n行二\r\n行三"})
        assert "\r" not in note["content"]
        await execute(registry, "update_note", USER_CTX,
                      {"note_id": note["id"], "content": "x\r\ny"})
        got = await execute(registry, "get_note", USER_CTX, {"note_id": note["id"]})
        assert got["content"] == "x\ny"

    async def test_query_excerpt_shows_hit_window(self, deps) -> None:
        filler = "前置文字" * 30  # 让命中点远超前 120 字
        await execute(registry, "create_note", USER_CTX,
                      {"title": "长文命中窗口", "content": filler + "命中词在这里附近"})
        hits = await execute(registry, "list_notes", USER_CTX, {"query": "命中词"})
        assert len(hits) == 1
        excerpt = hits[0]["excerpt"]
        assert excerpt.index("命中词") > 50  # 命中点在窗口中后段,而非固定开头

    async def test_validation_title_and_tag(self, deps) -> None:
        with pytest.raises(ServiceError):
            await execute(registry, "create_note", USER_CTX, {"title": "   "})
        with pytest.raises(ServiceError):
            await execute(registry, "rename_tag", USER_CTX,
                          {"old": 'a"b', "new": "c"})


class TestRegistryCard:
    def test_service_json_matches_registry(self) -> None:
        """模块卡能力清单必须与注册表一致(单一事实来源,§8.1)。"""
        import json as _json
        from pathlib import Path as _Path

        from services.notes.assets import register as register_assets

        register_assets(registry)
        card = _json.loads(
            (_Path(__file__).parent.parent / "service.json").read_text(encoding="utf-8"))
        assert set(card["capabilities"]) == set(registry.names())
