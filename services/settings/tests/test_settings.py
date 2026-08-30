"""settings 服务能力测试(§8.8):主题、聚合 schema、secret 边界、变更事件。"""

import pytest
from platform_capability import execute
from platform_contracts import ServiceError
from platform_settings import SettingDef, SettingType

from services.settings.capabilities import registry

from .conftest import AGENT_CTX, USER_CTX


class TestTheme:
    async def test_defaults(self, deps) -> None:
        out = await execute(registry, "get_theme", USER_CTX, {})
        # 工厂默认跟随系统(phase-06):用户显式浅/深之后只认设置
        assert out == {"theme": "system", "font_scale": 1.0, "code_font": "JetBrains Mono"}

    async def test_list_themes(self, deps) -> None:
        out = await execute(registry, "list_themes", AGENT_CTX, {})
        assert [t["id"] for t in out] == ["dark", "light", "system"]

    async def test_agent_can_switch_theme(self, deps) -> None:
        """铁律:用户能改的(agent 除隐私外)也能改。"""
        _store, log = deps
        out = await execute(registry, "set_theme", AGENT_CTX,
                            {"theme": "light", "font_scale": 1.2})
        assert out["theme"] == "light" and out["font_scale"] == 1.2
        changed = [e for _, e in log.read_after() if e.type == "settings.changed"]
        assert {e.payload["key"] for e in changed} == {
            "appearance.theme", "appearance.font_scale"}

    async def test_invalid_choice(self, deps) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "set_theme", USER_CTX, {"theme": "blue"})
        assert ei.value.body.code == "SETTINGS.INVALID_INPUT"

    async def test_empty_set_theme(self, deps) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "set_theme", USER_CTX, {})
        assert ei.value.body.code == "SETTINGS.INVALID_INPUT"


class TestAggregation:
    async def test_cross_module_schema(self, deps) -> None:
        """注册其他服务 defs 后,聚合输出按分组过滤(设置页动态渲染)。"""
        store, _ = deps
        store.register([SettingDef(key="notes.sort.default", module="notes",
                                   type=SettingType.CHOICE, default="updated",
                                   choices=("updated", "title"))])
        all_items = await execute(registry, "get_settings", USER_CTX, {})
        assert {i["module"] for i in all_items} >= {"appearance", "privacy", "notes"}
        notes_only = await execute(registry, "get_settings", USER_CTX,
                                   {"module": "notes"})
        assert [i["key"] for i in notes_only] == ["notes.sort.default"]

    async def test_get_setting(self, deps) -> None:
        item = await execute(registry, "get_setting", AGENT_CTX,
                             {"key": "privacy.activity_report"})
        assert item["value"] is True  # 行为上报默认开

    async def test_unknown_key(self, deps) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "get_setting", USER_CTX, {"key": "nope.nope"})
        assert ei.value.body.code == "SETTINGS.NOT_FOUND"


class TestSecretBoundary:
    @pytest.fixture()
    async def secret_key(self, deps) -> str:
        store, _ = deps
        store.register([SettingDef(key="privacy.test_secret", module="privacy",
                                   type=SettingType.STR, default="", secret=True)])
        return "privacy.test_secret"

    async def test_agent_write_secret_rejected(self, deps, secret_key) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "set_setting", AGENT_CTX,
                          {"key": secret_key, "value": "x"})
        assert ei.value.body.code == "SETTINGS.FORBIDDEN"

    async def test_user_write_secret_then_mask(self, deps, secret_key) -> None:
        item = await execute(registry, "set_setting", USER_CTX,
                             {"key": secret_key, "value": "plain-x"})
        assert item["secret"] and item["has_value"]
        assert "value" not in item  # secret 项不回值
