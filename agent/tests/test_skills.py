"""skill 体系测试(§9.13):索引常驻全文按需;重复流程自动整理需确认。"""

import pytest

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
