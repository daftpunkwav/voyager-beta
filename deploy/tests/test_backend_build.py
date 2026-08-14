"""聚合装配测试:build() 起全系统,/health 六域 up,能力经聚合入口可用。"""

from fastapi.testclient import TestClient

from deploy.backend import build

DOMAINS = {"llm", "sources", "notes", "graph", "settings", "agent"}


def test_build_health_and_domain_call(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert DOMAINS <= set(body["services"])
        assert all(s["status"] == "up" for s in body["services"].values())

        # web→gateway→服务链路:领域能力经聚合入口调用成功
        note = client.post("/api/notes/capabilities/create_note",
                           json={"title": "聚合链路测试"})
        assert note.status_code == 200
        assert note.json()["result"]["title"] == "聚合链路测试"


def test_agent_settings_in_shared_store(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    with TestClient(app) as client:
        items = client.post("/api/settings/capabilities/get_settings",
                            json={"module": "agent"}).json()["result"]
        keys = {item["key"] for item in items}
        assert "agent.style" in keys  # agent 设置项注册进共享 store,设置页可聚合


def test_domain_tools_reach_agent(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    backend = app.state.backend
    names = backend.agent.spawner._toolbelt.names()
    assert "notes__create_note" in names  # 领域能力已注入 agent 工具集
    assert "llm__complete" in names
