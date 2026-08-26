"""模板服务测试:能力调用、REST、长任务端到端(job + 事件)、service.json 一致性。"""

import json
import time
from pathlib import Path

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, DomainEvent, JobStatus
from platform_eventbus import EventBus, EventLog

from services._template.capabilities import registry
from services._template.store import JobStore

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from services._template.rest import create_app  # noqa: E402

USER_CTX = ActorContext(actor=LOCAL_USER)
SERVICE_DIR = Path(__file__).parent.parent


class TestCapabilities:
    async def test_echo(self) -> None:
        result = await execute(registry, "echo", USER_CTX, {"text": "hi", "shout": True})
        assert result == {"echo": "HI"}

    def test_service_json_matches_registry(self) -> None:
        """模块卡能力清单必须与注册表一致(单一事实来源,§8.1)。"""
        card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
        assert sorted(card["capabilities"]) == registry.names()


@pytest.fixture()
def app(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    application = create_app(tmp_path, bus=bus)
    application.state.event_log = log
    yield application
    log.close()


class TestRest:
    def test_health(self, app) -> None:
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "up"

    def test_echo_over_http(self, app) -> None:
        with TestClient(app) as client:
            resp = client.post("/capabilities/echo", json={"text": "hi"})
        assert resp.status_code == 200
        assert resp.json() == {"result": {"echo": "hi"}}


class TestJobFlow:
    def test_submit_job_end_to_end(self, app, tmp_path) -> None:
        """提交 → 202 → worker 执行 → 落库 completed + task.completed 事件。"""
        probe = JobStore(tmp_path / "template.db")  # 另开连接轮询,不依赖 app 内部
        with TestClient(app) as client:
            resp = client.post("/capabilities/submit_job", json={})
            assert resp.status_code == 202
            job_id = resp.json()["job"]["job_id"]
            deadline = time.time() + 5
            while time.time() < deadline:
                job = probe.get(job_id)
                if job and job["status"] == JobStatus.COMPLETED.value:
                    break
                time.sleep(0.05)
            else:
                pytest.fail("任务超时未完成")
        probe.close()
        log: EventLog = app.state.event_log
        completed = [e for _, e in log.read_after(types=[DomainEvent.TASK_COMPLETED])]
        assert any(e.payload["job_id"] == job_id for e in completed)
