"""聚合装配测试:build() 起全系统,/health 六域 up,能力经聚合入口可用。"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from platform_contracts import LOCAL_USER, ServiceError
from platform_settings import SettingsStore

from deploy.backend import ROOT, _resolve_workspace, build

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


class TestWorkspaceResolution:
    """工作目录解析(phase-10,§9.10):显式入参优先,否则读 agent.workspace.dir,
    相对路径拼仓库根;`..` 段与越出仓库根的绝对路径拒绝(phase-13 防越狱)。"""

    def _store(self, tmp_path, raw) -> SettingsStore:
        store = SettingsStore(tmp_path / "settings.db")
        from agent.settings import DEFS as AGENT_SETTING_DEFS

        store.register_fresh(AGENT_SETTING_DEFS)
        if raw is not None:
            asyncio.run(store.set("agent.workspace.dir", raw, LOCAL_USER))
        return store

    def test_explicit_dir_wins(self, tmp_path) -> None:
        store = self._store(tmp_path, "from_setting")
        assert _resolve_workspace(tmp_path / "explicit", store) == tmp_path / "explicit"

    def test_setting_relative_joins_root(self, tmp_path) -> None:
        store = self._store(tmp_path, "my/workspace")
        assert _resolve_workspace(None, store) == ROOT / "my" / "workspace"

    def test_empty_setting_falls_back_to_default(self, tmp_path) -> None:
        store = self._store(tmp_path, "")
        assert _resolve_workspace(None, store) == ROOT / "workspace"

    def test_dotdot_rejected(self, tmp_path) -> None:
        store = self._store(tmp_path, "../evil")
        with pytest.raises(ServiceError) as exc:
            _resolve_workspace(None, store)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    def test_absolute_root_rejected(self, tmp_path) -> None:
        """绝对盘根(C:\\ 或 /)拒绝,不静默回落默认目录。"""
        store = self._store(tmp_path, str(Path(ROOT.anchor)))
        with pytest.raises(ServiceError) as exc:
            _resolve_workspace(None, store)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    def test_absolute_outside_root_rejected(self, tmp_path) -> None:
        """同盘仓库外路径(D:\\evil)同样拒绝。"""
        outside = Path(ROOT.anchor) / "evil-ws"
        store = self._store(tmp_path, str(outside))
        with pytest.raises(ServiceError) as exc:
            _resolve_workspace(None, store)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    def test_absolute_inside_root_allowed(self, tmp_path) -> None:
        """仓库根之下的绝对路径放行(不是一刀切禁绝对路径)。"""
        inside = ROOT / "in-repo-ws"
        store = self._store(tmp_path, str(inside))
        assert _resolve_workspace(None, store) == inside
