"""用户自建 subagent 注册表测试(§9.4.4):校验、存取、列举、删除。"""

import pytest
from platform_contracts import ServiceError

from agent.subagent.registry import SubagentDef, SubagentRegistry


class TestDef:
    def test_valid_definition(self) -> None:
        d = SubagentDef(name="translator", description="翻译", mode="cot",
                        allowed_tools=("read_file",))
        assert d.trigger == "manual"

    def test_bad_name_rejected(self) -> None:
        with pytest.raises(ServiceError, match="snake_case"):
            SubagentDef(name="Bad Name", description="x")

    def test_unknown_mode_rejected(self) -> None:
        with pytest.raises(ServiceError, match="未知模式"):
            SubagentDef(name="ok_name", description="x", mode="magic")


class TestRegistry:
    def test_save_load_list_delete(self, tmp_path) -> None:
        reg = SubagentRegistry(tmp_path)
        reg.save(SubagentDef(name="alpha", description="A", mode="react"))
        reg.save(SubagentDef(name="beta", description="B", mode="tot",
                             scopes=("notes.read",)))
        loaded = reg.load("beta")
        assert loaded.mode == "tot" and loaded.scopes == ("notes.read",)
        assert [d.name for d in reg.list()] == ["alpha", "beta"]
        reg.delete("alpha")
        assert [d.name for d in reg.list()] == ["beta"]

    def test_load_unknown_raises(self, tmp_path) -> None:
        with pytest.raises(ServiceError, match="未注册"):
            SubagentRegistry(tmp_path).load("ghost")
