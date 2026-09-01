"""上下文工程测试(§9.12/§9.20):层序装配、压缩、页面感知、按需加载留痕。"""

from agent.context import (
    ContextBuilder,
    OnDemandLoader,
    PageContextRegistry,
    compress,
    estimate_tokens,
)
from agent.context.rules import GLOBAL_RULES
from agent.memory import Memory
from agent.personas import LUCIEN
from agent.skills.loader import SkillLoader
from agent.subagent import TaskBook


class TestGlobalRules:
    def test_shape_locked(self) -> None:
        """8 条原文(phase-28 自 main.py 抽出);只锁条数 + 首条前缀,不复制全文。"""
        assert len(GLOBAL_RULES) == 8
        assert GLOBAL_RULES[0].startswith("诚实第一")


class TestBuilder:
    def test_layer_order(self, tmp_path) -> None:
        memory = Memory(tmp_path)
        memory.profile.set("语言偏好", "中文")
        pages = PageContextRegistry()
        pages.update("notes", "36 条笔记")
        builder = ContextBuilder(
            rules=["诚实第一"], memory=memory, pages=pages
        )
        system = builder.system(
            persona=LUCIEN, task=TaskBook(goal="整理仓库", constraints="只读"), style="热心"
        )
        order = [
            system.index("【全局规则】"),
            system.index("【人格】"),
            system.index("【风格】"),
            system.index("【用户画像】"),
            system.index("【任务书】"),
            system.index("【用户当前页面】"),
        ]
        assert order == sorted(order)  # 层序:规则→人格→风格→画像→任务书→页面
        assert "诚实第一" in system and "整理仓库" in system and "只读" in system
        memory.close()


class TestCompressor:
    def test_under_budget_untouched(self) -> None:
        msgs = [{"role": "user", "content": "短"}]
        assert compress(msgs, budget=100) == msgs

    def test_tool_results_compressed_system_kept(self) -> None:
        msgs = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "任务"},
            {"role": "tool", "content": "很长的工具结果" * 200},
            {"role": "assistant", "content": "好"},
            {"role": "user", "content": "继续"},
            {"role": "assistant", "content": "在做"},
            {"role": "user", "content": "再查一下"},
            {"role": "assistant", "content": "马上"},
        ]
        out = compress(msgs, budget=100)
        assert out[0]["role"] == "system" and out[0]["content"] == "系统提示"
        assert estimate_tokens(out) < estimate_tokens(msgs)
        assert any("已压缩" in str(m.get("content", "")) for m in out)  # 最旧工具结果被截断

    def test_all_system_overflow_terminates(self) -> None:
        """极端场景:超预算但无可剪枝的非 system 消息,必须正常返回而非死循环。"""
        msgs = [{"role": "system", "content": "超长系统提示" * 500} for _ in range(9)]
        out = compress(msgs, budget=100)
        assert len(out) == 9  # system 永不压缩,但循环必须终止

    def test_prune_false_truncates_without_dropping(self) -> None:
        """prune=False 只截断不剪条目(phase-15):同一回合 transcript 上的
        assistant(tool_calls) 与 tool 对不能拆散,否则端点 400。"""
        msgs = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "任务"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
            {"role": "tool", "tool_call_id": "a", "content": "旧结果" * 300},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "b"}]},
            {"role": "tool", "tool_call_id": "b", "content": "新结果" * 300},
            {"role": "user", "content": "继续"},
            {"role": "assistant", "content": "收尾"},
            {"role": "user", "content": "再继续"},
        ]
        out = compress(msgs, budget=200, prune=False)
        assert len(out) == len(msgs)  # 只截断,条数不变
        assert "已压缩" in out[3]["content"]  # 旧 tool 被截断(末 4 条之外)
        assert out[5]["content"] == "新结果" * 300  # 最近 4 条内不动
        assert out[0]["content"] == "系统提示"  # system 保留


class TestPages:
    def test_update_and_render(self) -> None:
        pages = PageContextRegistry()
        assert "未知" in pages.render()
        pages.update("notes", "36 条笔记,当前打开《A》", counts={"notes": 36}, selected="第 3 段")
        pages.update("graph", "120 节点", counts={"nodes": 120})
        assert pages.current().page == "graph"  # 最近上报为当前页
        text = pages.render()
        assert "graph" in text and "nodes=120" in text


class TestOnDemandLoader:
    def test_loads_are_audited(self, tmp_path) -> None:
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# my-skill\n\n描述\n", encoding="utf-8")
        memory = Memory(tmp_path / "mem")
        memory.profile.set("兴趣", "图谱")
        pages = PageContextRegistry()
        pages.update("notes", "3 条笔记")
        loader = OnDemandLoader(
            skills=SkillLoader([tmp_path]), memory=memory, pages=pages
        )
        assert "描述" in loader.skill_text("my-skill")
        assert loader.recall("图谱")[0]["from"] == "profile"
        assert "notes" in loader.page_summary()
        assert [r["kind"] for r in loader.loads] == ["skill", "memory", "page"]  # 加载留痕
        memory.close()
