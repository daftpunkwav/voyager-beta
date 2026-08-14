"""把服务目录加入 sys.path,并装配测试用 gateway(挂一个内存 echo 服务)。"""

import sys
from pathlib import Path

import pytest
from platform_capability import Registry, capability
from platform_eventbus import EventBus, EventLog

sys.path.insert(0, str(Path(__file__).parent.parent))

from mounts import MountSpec
from rest import create_app

_echo_registry = Registry("echo")


@capability(_echo_registry, name="echo", description="回显")
def echo(text: str) -> dict:
    return {"text": text}


@capability(_echo_registry, name="explode", description="必失败")
def explode() -> dict:
    from platform_contracts import ErrorSuffix, ServiceError
    raise ServiceError("echo", ErrorSuffix.UNAVAILABLE, "echo 服务挂了")


@pytest.fixture()
def bus(tmp_path):
    return EventBus(EventLog(tmp_path / "events.db"))


@pytest.fixture()
def app(bus, tmp_path):
    return create_app(
        [MountSpec(domain="echo", registry=_echo_registry,
                   probe=lambda: {"status": "up"})],
        bus=bus, db_path=tmp_path / "gw.db",
    )
