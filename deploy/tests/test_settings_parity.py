"""设置写权限 parity(§8.8):agent 经桥与用户同权改设置;secret 项仅用户可写。

- agent 调 settings__set_setting 改普通项 → 成功,settings.changed 事件 actor 为 agent;
- agent 写 secret 项 → SETTINGS.FORBIDDEN;
- user 写 secret 项 → 成功,schema 出口只有 has_value,不回 value/default。
"""

from fastapi.testclient import TestClient

from agent.llm import ToolCall
from deploy.backend import build
from platform_settings import SettingDef, SettingType

_SECRET_KEY = "test.secret_token"


def _backend(tmp_path):
    app = build(tmp_path / "data", tmp_path / "ws")
    # 测试专用 secret 项(动态注册,不进任何服务 defs,不污染生产 schema)
    app.state.backend.settings_store.register([
        SettingDef(key=_SECRET_KEY, module="test", type=SettingType.STR,
                   default="", secret=True, description="测试 secret 项"),
    ])
    return app


class TestAgentParity:
    async def test_agent_sets_theme_event_carries_agent_actor(self, tmp_path) -> None:
        app = _backend(tmp_path)
        backend = app.state.backend
        belt = backend.agent.spawner._toolbelt
        with TestClient(app):
            out = await belt.call(ToolCall(
                id="t1", name="settings__set_setting",
                arguments={"key": "appearance.theme", "value": "light"},
            ))
            assert "工具失败" not in out and "已拒绝" not in out
            events = [e for _, e in backend.log.read_after(types=["settings.changed"])]
            assert events, "settings.changed 未发布"
            last = events[-1]
            assert last.actor.kind.value == "agent"  # agent 写入,事件可审计溯源
            assert last.payload["key"] == "appearance.theme"
            assert last.payload["value"] == "light"
            assert backend.settings_store.get("appearance.theme") == "light"

    async def test_agent_cannot_write_secret(self, tmp_path) -> None:
        app = _backend(tmp_path)
        belt = app.state.backend.agent.spawner._toolbelt
        with TestClient(app):
            out = await belt.call(ToolCall(
                id="t1", name="settings__set_setting",
                arguments={"key": _SECRET_KEY, "value": "sk-agent"},
            ))
            # 框架层守卫:secret 仅用户,agent 经同一能力入口同样被拒
            # (toolbelt 把 ServiceError 转为文本结果,码见消息语义)
            assert "仅用户本人可写" in out
            assert app.state.backend.settings_store.get(_SECRET_KEY) == ""


class TestUserSecret:
    def test_user_writes_secret_schema_hides_value(self, tmp_path) -> None:
        app = _backend(tmp_path)
        with TestClient(app) as client:
            resp = client.post("/api/settings/capabilities/set_setting",
                               json={"key": _SECRET_KEY, "value": "sk-user"})
            item = resp.json()["result"]
            assert item["has_value"] is True
            assert "value" not in item and "default" not in item  # 值永不出 schema

            items = client.post("/api/settings/capabilities/get_settings",
                                json={"module": "test"}).json()["result"]
            assert items[0]["key"] == _SECRET_KEY
            assert items[0]["has_value"] is True
            assert "value" not in items[0]
