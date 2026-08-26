"""code-exec 服务测试:能力、REST、host 回退执行、安全校验、service.json 一致性。"""

import json
from pathlib import Path

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

from services.code_exec.capabilities import registry
from services.code_exec.executor import run_in_runtime
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


class TestSecurity:
    async def test_run_file_rejects_traversal(self, app) -> None:
        for bad in ("../../secrets.txt", "sub/../../escape.py"):
            with pytest.raises(ServiceError) as exc:
                await execute(registry, "run_file", USER_CTX,
                              {"runtime": "python", "file_path": bad})
            assert exc.value.body.code == "CODE_EXEC.INVALID_INPUT"

    async def test_run_file_missing_404(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "run_file", USER_CTX,
                          {"runtime": "python", "file_path": "nope.py"})
        assert exc.value.body.code == "CODE_EXEC.NOT_FOUND"

    async def test_runtime_rejects_shell_metachars(self, tmp_path) -> None:
        """镜像/命令/后缀含注入字符时,校验在任何执行路径之前拒绝。"""
        poisoned_image = {"id": "python", "image": "python:3.11; touch pwned",
                          "file_ext": ".py", "cmd": ["python"]}
        with pytest.raises(ServiceError, match="镜像"):
            await run_in_runtime(poisoned_image, "print(1)", timeout=5, memory_mb=64,
                                 network=False, use_host_fallback=True,
                                 workspace=tmp_path)
        poisoned_ext = {"id": "python", "image": "python:3.11-slim",
                        "file_ext": "../x.py", "cmd": ["python"]}
        with pytest.raises(ServiceError, match="后缀"):
            await run_in_runtime(poisoned_ext, "print(1)", timeout=5, memory_mb=64,
                                 network=False, use_host_fallback=True,
                                 workspace=tmp_path)
        poisoned_cmd = {"id": "python", "image": "python:3.11-slim",
                        "file_ext": ".py", "cmd": ["python", "-c 'boom'"]}
        with pytest.raises(ServiceError, match="命令"):
            await run_in_runtime(poisoned_cmd, "print(1)", timeout=5, memory_mb=64,
                                 network=False, use_host_fallback=True,
                                 workspace=tmp_path)

    async def test_host_fallback_only_known_interpreters(
            self, tmp_path, monkeypatch) -> None:
        """宿主回退只认 python/node/shell;自定义运行时必须走 docker。"""
        from services.code_exec import executor
        monkeypatch.setattr(executor.shutil, "which", lambda name: None)  # 视为无 docker
        custom = {"id": "custom", "image": "x:1", "file_ext": ".txt",
                  "cmd": ["whatever"]}
        with pytest.raises(ServiceError, match="宿主回退"):
            await run_in_runtime(custom, "hi", timeout=5, memory_mb=64,
                                 network=False, use_host_fallback=True,
                                 workspace=tmp_path)
