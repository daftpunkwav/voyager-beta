"""设置项框架测试:默认值、校验、secret 写保护、变更事件、schema 渲染。"""

import pytest
from platform_contracts import ActorKind, ActorRef, DomainEvent, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingDef, SettingsStore, SettingType

USER = ActorRef(kind=ActorKind.USER, id="local")
AGENT = ActorRef(kind=ActorKind.AGENT, id="agent.main")

DEFS = [
    SettingDef(key="agent.rounds.max", module="agent", type=SettingType.INT, default=20, min=1, max=200),
    SettingDef(key="agent.arbiter.mode", module="agent", type=SettingType.CHOICE,
               default="queue", choices=("auto", "queue", "guide")),
    SettingDef(key="ui.theme", module="ui", type=SettingType.STR, default="dark"),
    SettingDef(key="llm.kimi.api_key", module="llm", type=SettingType.STR,
               default="", secret=True),
]


@pytest.fixture()
def store(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    st = SettingsStore(tmp_path / "settings.db", bus=bus)
    st.register(DEFS)
    yield st, log
    st.close()
    log.close()


class TestBasics:
    def test_default(self, store) -> None:
        st, _ = store
        assert st.get("agent.rounds.max") == 20

    async def test_set_get_and_persist(self, store, tmp_path) -> None:
        st, _ = store
        await st.set("ui.theme", "light", USER)
        assert st.get("ui.theme") == "light"
        reopened = SettingsStore(tmp_path / "settings.db")
        reopened.register(DEFS)
        assert reopened.get("ui.theme") == "light"  # 落库持久
        reopened.close()

    def test_unknown_key(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="未知设置项"):
            st.get("nope.key")

    def test_duplicate_register(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="重复注册"):
            st.register(DEFS)


class TestValidation:
    async def test_type_check(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="int 类型"):
            await st.set("agent.rounds.max", True, USER)

    async def test_range_check(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="不能大于 200"):
            await st.set("agent.rounds.max", 999, USER)

    async def test_choice_check(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="取值须属于"):
            await st.set("agent.arbiter.mode", "yolo", USER)
        await st.set("agent.arbiter.mode", "auto", USER)
        assert st.get("agent.arbiter.mode") == "auto"


class TestSecret:
    async def test_agent_write_forbidden(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError) as exc:
            await st.set("llm.kimi.api_key", "sk-xxx", AGENT)
        assert exc.value.body.code == "SETTINGS.FORBIDDEN"
        assert exc.value.http_status == 403

    async def test_user_write_ok_and_schema_redacted(self, store) -> None:
        st, _ = store
        await st.set("llm.kimi.api_key", "sk-xxx", USER)
        schema = {item["key"]: item for item in st.list_schema()}
        secret_item = schema["llm.kimi.api_key"]
        assert secret_item["has_value"] is True
        assert "value" not in secret_item  # secret 不回值
        theme = schema["ui.theme"]
        assert theme["value"] == "dark"

    async def test_change_event_omits_secret_value(self, store) -> None:
        st, log = store
        await st.set("ui.theme", "light", USER)
        await st.set("llm.kimi.api_key", "sk-yyy", USER)
        events = [e for _, e in log.read_after(types=[DomainEvent.SETTINGS_CHANGED])]
        assert len(events) == 2
        assert events[0].payload["value"] == "light"  # 非 secret 带值
        assert "value" not in events[1].payload  # secret 不带值
        assert events[1].payload["secret"] is True
        assert events[0].actor == USER
