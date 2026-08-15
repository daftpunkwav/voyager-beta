"""活动流集成:跑一串操作(建笔记/改设置/发消息/删笔记)-> feed 按 seq
升序返回全部事件、types 过滤生效;补偿撤销(note.created -> delete_note)
产生 note.deleted 且 actor 为用户。
"""

from fastapi.testclient import TestClient

from deploy.backend import build


def _seqs(events: list[dict]) -> list[int]:
    return [e["seq"] for e in events]


def test_feed_ascending_and_type_filter(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws", llm=_noop_llm())
    with TestClient(app) as client:
        note = client.post("/api/notes/capabilities/create_note",
                           json={"title": "活动页测试"}).json()["result"]
        client.post("/api/settings/capabilities/set_setting",
                    json={"key": "notes.sort.default", "value": "created"})
        client.post("/api/chat/messages", json={"content": "在吗"})
        client.post("/api/notes/capabilities/delete_note",
                    json={"note_id": note["id"]})

        feed = client.get("/api/activity/feed").json()["events"]
        types = [e["type"] for e in feed]
        assert "note.created" in types
        assert "settings.changed" in types
        assert "user.message" in types
        assert "note.deleted" in types
        assert _seqs(feed) == sorted(_seqs(feed))  # 升序
        assert len(set(_seqs(feed))) == len(feed)  # seq 全序不重复

        # types 过滤:只回笔记创建
        only = client.get("/api/activity/feed?types=note.created").json()["events"]
        assert only and all(e["type"] == "note.created" for e in only)
        assert all(e["payload"]["title"] == "活动页测试" for e in only)

        # after_seq 游标:从中间翻页不重不漏
        mid = only[0]["seq"]
        rest = client.get(f"/api/activity/feed?after_seq={mid}").json()["events"]
        assert all(e["seq"] > mid for e in rest)


def test_compensation_undo_note_created(tmp_path) -> None:
    """撤销 note.created = delete_note(反向能力):列表消失 + note.deleted 追加。"""
    app = build(tmp_path / "data", tmp_path / "ws", llm=_noop_llm())
    with TestClient(app) as client:
        note = client.post("/api/notes/capabilities/create_note",
                           json={"title": "将被撤销"}).json()["result"]
        out = client.post("/api/notes/capabilities/list_notes", json={}).json()["result"]
        assert any(s["id"] == note["id"] for s in out)

        # 补偿动作(活动页撤销按钮背后就是这个调用;actor=本地用户)
        client.post("/api/notes/capabilities/delete_note",
                    json={"note_id": note["id"]})
        out = client.post("/api/notes/capabilities/list_notes", json={}).json()["result"]
        assert all(s["id"] != note["id"] for s in out)

        deleted = client.get("/api/activity/feed?types=note.deleted").json()["events"]
        assert deleted and deleted[-1]["payload"]["title"] == "将被撤销"


def _noop_llm():
    """极简 LLM:chat 消息不驱动真实 agent(避免无 key 降级路径的不确定性)。"""
    from agent.llm import FakeLLM

    return FakeLLM(default="嗯。")
