"""总览页聚合契约冒烟:build() 后六个数据源全部可拉
(/health、activity feed、用量、索引任务、资源库、笔记)。
总览页零新增接口——此测试钉住它依赖的既有接口不被破坏。
"""

from fastapi.testclient import TestClient

from agent.llm import FakeLLM
from deploy.backend import build

SOURCES = [
    ("GET", "/health", None),
    ("GET", "/api/activity/feed?limit=10", None),
    ("POST", "/api/llm/capabilities/get_usage_stats", {"days": 7}),
    ("POST", "/api/graph/capabilities/list_index_jobs", {}),
    ("POST", "/api/sources/capabilities/list_repos", {}),
    ("POST", "/api/notes/capabilities/list_notes", {"limit": 500}),
]


def test_overview_contract_smoke(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws", llm=FakeLLM(default="嗯"))
    with TestClient(app) as client:
        # 造一点数据(笔记 + 一条用户消息),卡片才有内容可渲染
        client.post("/api/notes/capabilities/create_note", json={"title": "总览冒烟"})
        client.post("/api/chat/messages", json={"content": "在吗"})

        for method, url, body in SOURCES:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json=body)
            assert resp.status_code == 200, f"{url} -> {resp.status_code}: {resp.text[:200]}"

        # 各数据源的关键字段形态(卡片渲染依赖)
        health = client.get("/health").json()
        assert "services" in health
        feed = client.get("/api/activity/feed?limit=10").json()["events"]
        assert any(e["type"] == "note.created" for e in feed)
        usage = client.post("/api/llm/capabilities/get_usage_stats",
                            json={"days": 7}).json()["result"]
        assert {"input_tokens", "output_tokens", "calls", "by_model"} <= set(usage)
        notes = client.post("/api/notes/capabilities/list_notes",
                            json={"limit": 500}).json()["result"]
        assert any(n["title"] == "总览冒烟" for n in notes)
