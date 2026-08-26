"""把服务目录加入 sys.path(服务为非包扁平模块),并注入依赖。"""

import sys
from pathlib import Path

import pytest
from platform_actor import ActorContext
from platform_contracts import ActorKind, ActorRef
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 仓库根

from services.settings import capabilities
from services.settings.capabilities import Deps
from services.settings.settings import DEFS

USER_CTX = ActorContext(actor=ActorRef(kind=ActorKind.USER, id="user.local"))
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
async def deps(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    store = SettingsStore(tmp_path / "settings.db", bus)
    store.register(DEFS)
    capabilities.init_deps(Deps(store=store))
    yield store, log
    store.close()
