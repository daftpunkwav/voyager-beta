"""code-exec 服务测试:能力、REST、host 回退执行、service.json 一致性。"""

import json
from pathlib import Path

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

from services.code_exec.capabilities import registry
from services.code_exec.rest import create_app

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

USER_CTX = ActorContext(actor=LOCAL_USER)
SERVICE_DIR = Path(__file__).parent.parent


@pytest.fixture()
def app(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    settings_store = SettingsStore(tmp_path / "settings.db", bus)
    application = create_app(tmp_path, workspace=workspace, bus=bus,
                             settings_store=settings_store)
    application.state.settings_store = settings_store
    application.state.event_log = log
    yield application
    log.close()
    settings_store.close()


class TestCapabilities:
    async def test_list_runtimes(self, app) -> None:
        result = await execute(registry, "list_runtimes", USER_CTX, {})
        assert isinstance(result, list)
        assert any(r["id"] == "python" for r in result)

    def test_service_json_matches_registry(self) -> None:
        card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
        assert sorted(card["capabilities"]) == registry.names()


class TestRest:
    def test_health(self, app) -> None:
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "up"

    def test_run_snippet_returns_job(self, app) -> None:
        with TestClient(app) as client:
            resp = client.post("/capabilities/run_snippet", json={
                "runtime": "python",
                "code": "print('hello')",
            })
        assert resp.status_code == 202
        assert "job_id" in resp.json()["job"]
