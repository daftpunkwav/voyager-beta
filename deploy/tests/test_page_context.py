"""页面感知集成:report_page_context 落 agent 的 PageContextRegistry,
master 上下文装配含该摘要(agent 据此回答"用户在看什么")。
"""

from fastapi.testclient import TestClient

from agent.llm import FakeLLM
from deploy.backend import build


def test_page_context_reaches_agent(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws", llm=FakeLLM(default="嗯"))
    with TestClient(app) as client:
        out = client.post("/api/agent/capabilities/report_page_context", json={
            "page": "notes",
            "summary": "36 篇笔记,当前打开《langgraph 笔记》",
            "counts": {"notes": 36},
            "selected": "langgraph 笔记",
        }).json()["result"]
        assert out == {"page": "notes", "ok": True}

        # 注册表读回:current 指向该页,渲染摘要含计数与选中项
        agent_app = app.state.backend.agent
        pages = agent_app.pages
        assert pages.current() is not None
        assert pages.current().page == "notes"
        rendered = pages.render()
        assert "36 篇笔记" in rendered
        assert "notes=36" in rendered
        assert "当前选中: langgraph 笔记" in rendered

        # 上下文装配(§9.12):builder 输出含"用户当前页面"层
        system = agent_app.master._spawner._build_system(None, "lucien")  # 装配产物句柄
        assert "用户当前页面" in system and "36 篇笔记" in system


def test_activity_report_event_chain(tmp_path) -> None:
    """行为上报 -> user.activity 事件进流(Observer 的输入;前端开关只控制发不发)。"""
    app = build(tmp_path / "data2", tmp_path / "ws2", llm=FakeLLM(default="嗯"))
    backend = app.state.backend
    with TestClient(app) as client:
        resp = client.post("/api/activity", json={
            "kind": "page_view", "page": "/notes", "detail": {},
        })
        assert resp.status_code == 200 and resp.json()["seq"] > 0
        events = [e for _, e in backend.log.read_after(types=["user.activity"])]
        assert events and events[-1].payload["page"] == "/notes"
