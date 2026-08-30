"""skill 体系测试(§9.13):索引常驻全文按需;重复流程自动整理需确认。"""

import pytest

from agent.context import ContextBuilder
from agent.memory.episodic import EpisodicMemory
from agent.skills.loader import SkillLoader
from agent.skills.organizer import SkillOrganizer


def _make_skill(root, name: str, desc: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"# {name}\n\n{desc}\n\n## 步骤\n1. …\n", encoding="utf-8")


class TestLoader:
    def test_index_resident_full_on_demand(self, tmp_path) -> None:
        _make_skill(tmp_path, "explore-repo", "探索仓库结构")
        _make_skill(tmp_path, "summarize", "总结材料")
        loader = SkillLoader([tmp_path, tmp_path / "不存在"])
        index = loader.index()
        assert [i["name"] for i in index] == ["explore-repo", "summarize"]
        assert index[0]["description"] == "explore-repo"  # 首行标题
        assert "探索仓库结构" in loader.full_text("explore-repo")

    def test_unknown_skill_raises(self, tmp_path) -> None:
        with pytest.raises(KeyError, match="未知 skill"):
            SkillLoader([tmp_path]).full_text("nope")


class TestIndexVisibility:
    """phase-11:索引进上下文、不泄漏本机路径;插件示例不进默认索引。"""

    def test_index_entries_have_no_path(self, tmp_path) -> None:
        _make_skill(tmp_path, "my-skill", "做一件事")
        for entry in SkillLoader([tmp_path]).index():
            assert set(entry) == {"name", "description"}  # path 不出 loader

    def test_builder_injects_skill_layer(self, tmp_path) -> None:
        # _read_desc 取首行作描述:首行即「一句话描述」,与真实 skill 文件一致
        d = tmp_path / "explore-repo"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "# 探索仓库结构\n\n了解一个仓库的流程:…\n", encoding="utf-8"
        )
        builder = ContextBuilder(skills=SkillLoader([tmp_path]))
        system = builder.system()
        assert "【可用 skill】" in system
        assert "explore-repo: 探索仓库结构" in system
        assert "load_skill" in system  # 指路按需取全文
        assert str(tmp_path) not in system  # 不泄漏本机绝对路径

    def test_builder_omits_layer_when_no_skills(self, tmp_path) -> None:
        builder = ContextBuilder(skills=SkillLoader([tmp_path / "空"]))
        assert "【可用 skill】" not in builder.system()


class TestDefaultWiring:
    """build_agent 默认 roots:内置 + 用户 skills 目录;插件 _example 不进。"""

    def _build(self, tmp_path):
        from agent.llm import FakeLLM
        from agent.main import build_agent

        return build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )

    def test_builtin_in_user_example_out(self, tmp_path) -> None:
        app = self._build(tmp_path)
        try:
            names = [e["name"] for e in app.skills.index()]
            assert "explore-repo" in names  # 内置 skill 入库
            assert "daily-note" not in names  # plugins/_example 未经批准不进索引
        finally:
            app.memory.close()

    def test_user_skill_dir_discovered(self, tmp_path) -> None:
        d = tmp_path / "ws" / "skills" / "my-workflow"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# my-workflow\n\n三步收尾流程\n", encoding="utf-8")
        app = self._build(tmp_path)
        try:
            assert "my-workflow" in [e["name"] for e in app.skills.index()]
        finally:
            app.memory.close()

    async def test_spawned_system_contains_skill_index(self, tmp_path) -> None:
        from agent.subagent import Mode, TaskBook

        app = self._build(tmp_path)
        try:
            inst = app.spawner.spawn(
                TaskBook(goal="测试", mode=Mode.REACT), persona="orchestrator"
            )
            assert "【可用 skill】" in inst.system_prompt
            assert "explore-repo: explore-repo(skill 内置示例)" in inst.system_prompt
        finally:
            app.memory.close()


class TestOrganizer:
    def _fill(self, db, runs: int = 3) -> EpisodicMemory:
        ep = EpisodicMemory(db)
        for i in range(runs):
            ep.log("tool", "read_file", run_id=f"r{i}")
            ep.log("tool", "write_file", run_id=f"r{i}")
        return ep

    def test_detect_repeated_sequence(self, tmp_path) -> None:
        ep = self._fill(tmp_path / "ep.db")
        org = SkillOrganizer(ep, tmp_path / "skills")
        hits = ep and org.detect(min_count=3, seq_len=2)
        assert hits == [{"sequence": ["read_file", "write_file"], "count": 3}]
        assert org.detect(min_count=4) == []  # 不够次数不报

    async def test_propose_saves_after_confirm(self, tmp_path) -> None:
        ep = self._fill(tmp_path / "ep.db")

        async def yes(_prompt: str) -> bool:
            return True

        org = SkillOrganizer(ep, tmp_path / "skills", confirm=yes)
        saved = await org.propose_and_save(min_count=3)
        assert len(saved) == 1
        text = saved[0].read_text(encoding="utf-8")
        assert "共出现 3 次" in text and "read_file" in text

    async def test_user_decline_skips(self, tmp_path) -> None:
        ep = self._fill(tmp_path / "ep.db")

        async def no(_prompt: str) -> bool:
            return False

        org = SkillOrganizer(ep, tmp_path / "skills", confirm=no)
        assert await org.propose_and_save(min_count=3) == []
        assert not (tmp_path / "skills").exists()
