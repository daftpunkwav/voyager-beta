"""导入全链路集成:HTTP 导入 -> worker 克隆(注入 clone_fn) -> 事件链完整。

source.added -> task.progress -> source.ready;agent 侧经桥同样可导入;
remove_repo 落库后本地克隆目录异步清理(worker remove 通道)。
"""

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from deploy.backend import build
from services.sources.modules.repo import github as github_mod

_TOKEN = "x" * 40


@pytest.fixture()
def fake_github(monkeypatch):
    """import_repo 的元数据/README 拉取走 MockTransport,不触网。"""
    import base64

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "encoding": "base64",
            "content": base64.b64encode(b"# Fake README").decode(),
        })

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        github_mod.httpx, "AsyncClient",
        lambda **kw: orig(transport=httpx.MockTransport(handler), **kw),
    )
    return _TOKEN


def _fake_clone(dests: list):
    async def clone(owner: str, name: str, dest) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.mkdir(exist_ok=True)
        (dest / "HEAD").write_text("fake clone", encoding="utf-8")
        dests.append(dest)
    return clone


def _wait(log, types, *, timeout=8.0, pred=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = [e for _, e in log.read_after(types=types)
                  if pred is None or pred(e)]
        if events:
            return events
        time.sleep(0.05)
    raise AssertionError(f"等待事件超时: {types}")


class TestImportChain:
    def test_full_event_chain(self, tmp_path, fake_github, monkeypatch) -> None:
        """导入 -> source.added -> task.progress(clone) -> source.ready -> 状态 ready。"""
        dests: list = []
        app = build(tmp_path / "data", tmp_path / "ws", clone_fn=_fake_clone(dests))
        backend = app.state.backend
        with TestClient(app) as client:
            # import_repo 需要元数据拉取(fake_github 只覆盖 readme 路径;
            # 元数据另补一个通用应答)
            resp = client.post("/api/sources/capabilities/import_repo", json={
                "url": "https://github.com/langchain-ai/langgraph",
                "category": "Agent 框架",
            })
            assert resp.status_code == 202
            rid = resp.json()["job"]["job_id"]

            _wait(backend.log, ["source.added"],
                  pred=lambda e: e.payload["source_id"] == rid)
            _wait(backend.log, ["task.progress"],
                  pred=lambda e: e.payload.get("stage") == "done")
            ready = _wait(backend.log, ["source.ready"],
                          pred=lambda e: e.payload["source_id"] == rid)
            assert ready[-1].payload["repo"] == "langchain-ai/langgraph"

            repos = client.post("/api/sources/capabilities/list_repos",
                                json={}).json()["result"]
            mine = next(r for r in repos if r["id"] == rid)
            assert mine["status"] == "ready"
            assert mine["category"] == "Agent 框架"
            assert str(dests[0]).endswith("langchain-ai__langgraph")

    def test_remove_cleans_local_clone(self, tmp_path, fake_github, monkeypatch) -> None:
        """remove_repo:记录消失 + 本地克隆目录被 worker 异步清理。"""
        dests: list = []
        app = build(tmp_path / "data", tmp_path / "ws", clone_fn=_fake_clone(dests))
        backend = app.state.backend
        with TestClient(app) as client:
            rid = client.post("/api/sources/capabilities/import_repo", json={
                "url": "https://github.com/psf/requests",
            }).json()["job"]["job_id"]
            _wait(backend.log, ["source.ready"],
                  pred=lambda e: e.payload["source_id"] == rid)

            local = dests[0]
            assert local.exists()
            client.post("/api/sources/capabilities/remove_repo", json={"repo_id": rid})
            deadline = time.time() + 5
            while time.time() < deadline and local.exists():
                time.sleep(0.05)  # worker 异步删除
            assert not local.exists(), "本地克隆目录未被清理"
            repos = client.post("/api/sources/capabilities/list_repos",
                                json={}).json()["result"]
            assert all(r["id"] != rid for r in repos)
