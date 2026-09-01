"""用户自建 subagent 注册表测试(§9.4.4):校验、存取、列举、删除。"""

import json

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

    def test_load_delete_reject_traversal(self, tmp_path) -> None:
        # root 外放一份合法形状 JSON,`../pwn` 不得读/删到它
        (tmp_path / "pwn.json").write_text(
            json.dumps({"name": "pwn", "description": "x", "mode": "react"}),
            encoding="utf-8",
        )
        reg = SubagentRegistry(tmp_path / "sub")
        with pytest.raises(ServiceError, match="snake_case"):
            reg.load("../pwn")
        with pytest.raises(ServiceError, match="snake_case"):
            reg.delete("../pwn")
        assert (tmp_path / "pwn.json").exists()

    def test_load_rejects_non_snake_case(self, tmp_path) -> None:
        with pytest.raises(ServiceError, match="snake_case"):
            SubagentRegistry(tmp_path).load("Bad Name")

    def test_list_skips_bad_files(self, tmp_path) -> None:
        # 单份坏 JSON / 非法定义不挡 list();坏文件保留在磁盘不删
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        reg = SubagentRegistry(tmp_path)
        reg.save(SubagentDef(name="alpha", description="A", mode="react"))
        (tmp_path / "zzz-bad-mode.json").write_text(
            json.dumps({"name": "zzz", "description": "x", "mode": "magic"}),
            encoding="utf-8",
        )
        assert [d.name for d in reg.list()] == ["alpha"]
        # 坏文件未被删除、内容未改
        assert (tmp_path / "broken.json").read_text(encoding="utf-8") == "{not json"
        assert (tmp_path / "zzz-bad-mode.json").exists()
