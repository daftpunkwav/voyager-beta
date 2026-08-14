"""gateway 测试:服务挂载与错误体、chat 通道、SSE、限流、行为上报、健康聚合。"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, DomainEvent, Event

from services.gateway.rest import create_app

from .conftest import MountSpec, _echo_registry


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


class TestMount:
    def test_capability_call(self, client) -> None:
        r = client.post("/api/echo/capabilities/echo", json={"text": "hi"})
        assert r.status_code == 200
        assert r.json()["result"] == {"text": "hi"}

    def test_service_error_envelope(self, client) -> None:
        """统一错误体(§7.10):图谱挂了,前端拿到的就是 GRAPH.UNAVAILABLE 这种形态。"""
        r = client.post("/api/echo/capabilities/explode", json={})
        assert r.status_code == 503
        body = r.json()["error"]
        assert body["code"] == "ECHO.UNAVAILABLE" and body["service"] == "echo"


class TestChat:
    def test_post_and_history(self, client, bus) -> None:
        r = client.post("/api/chat/messages", json={"content": "你好"})
        assert r.status_code == 200 and r.json()["seq"] >= 1
        asyncio.run(bus.publish(Event(
            type=DomainEvent.AGENT_MESSAGE,
            actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
            payload={"content": "你好,我在"},
        )))
        r = client.get("/api/chat/messages")
        msgs = [(m["type"], m["payload"]["content"]) for m in r.json()["messages"]]
        assert msgs == [("user.message", "你好"), ("agent.message", "你好,我在")]

    def test_empty_message_rejected(self, client) -> None:
        r = client.post("/api/chat/messages", json={"content": "  "})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "GATEWAY.INVALID_INPUT"

    def test_sse_replay_then_close(self, client, bus) -> None:
        """断线续传:带 after_seq 连流,先补日志里的存量事件(once 模式追平即关)。"""
        asyncio.run(bus.publish(Event(
            type=DomainEvent.AGENT_MESSAGE,
            actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
            payload={"content": "离线时的回复"},
        )))
        r = client.get("/api/chat/stream?after_seq=0&once=true")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "离线时的回复" in r.text
        assert "id: 1" in r.text  # 帧带 seq,客户端续传凭据


class TestRateLimit:
    def test_per_minute_cap(self, bus, tmp_path) -> None:
        app = create_app([MountSpec(domain="echo", registry=_echo_registry)],
                         bus=bus, db_path=tmp_path / "gw.db",
                         rate_limit_per_minute=2)
        with TestClient(app) as c:
            assert c.post("/api/chat/messages", json={"content": "1"}).status_code == 200
            assert c.post("/api/chat/messages", json={"content": "2"}).status_code == 200
            r = c.post("/api/chat/messages", json={"content": "3"})
            assert r.status_code == 429
            assert r.json()["error"]["code"] == "GATEWAY.RATE_LIMITED"


class TestActivity:
    def test_report_and_feed(self, client) -> None:
        r = client.post("/api/activity",
                        json={"kind": "page_view", "page": "notes",
                              "detail": {"note_count": 5}})
        assert r.status_code == 200
        feed = client.get("/api/activity/feed?types=user.activity").json()["events"]
        assert feed[-1]["payload"]["page"] == "notes"

    def test_unknown_kind(self, client) -> None:
        r = client.post("/api/activity", json={"kind": "hack"})
        assert r.status_code == 400

    def test_online(self, client) -> None:
        assert client.post("/api/user/online").status_code == 200


class TestHealth:
    def test_aggregate_and_transition_event(self, bus, tmp_path) -> None:
        state = {"up": True}

        def probe():
            if state["up"]:
                return {"status": "up"}
            raise RuntimeError("connection refused")

        app = create_app([MountSpec(domain="echo", registry=_echo_registry,
                                    probe=probe)],
                         bus=bus, db_path=tmp_path / "gw.db")
        with TestClient(app) as c:
            r = c.get("/health").json()
            assert r["status"] == "up" and r["services"]["echo"]["status"] == "up"
            state["up"] = False
            r = c.get("/health").json()
            assert r["status"] == "degraded"
            assert r["services"]["echo"]["status"] == "down"
        types = [e.type for _, e in bus.log.read_after()]
        assert DomainEvent.SERVICE_HEALTH_CHANGED in types

    def test_actor_middleware_defaults_local(self, client) -> None:
        """无令牌按本地单用户(§7.4)。"""
        assert LOCAL_USER.id == "local"
