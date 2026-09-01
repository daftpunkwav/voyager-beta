"""上下文工程测试(§9.12/§9.20):层序装配、压缩、页面感知、按需加载留痕。"""

from agent.context import (
    ContextBuilder,
    OnDemandLoader,
    PageContextRegistry,
    compress,
    estimate_tokens,
)
from agent.context.compressor import _prune_span
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

    @staticmethod
    def _tool_pair_msgs() -> list[dict]:
        """多组 user → assistant(tool_calls) → tool 的合法 transcript(超预算)。"""
        def long(text: str) -> str:
            return text * 20

        return [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": long("第一轮任务")},
            {"role": "assistant", "content": long("调一个工具"), "tool_calls": [{"id": "a1"}]},
            {"role": "tool", "tool_call_id": "a1", "content": long("第一组结果")},
            {"role": "assistant", "content": long("第一轮小结")},
            {"role": "user", "content": long("第二轮任务")},
            {"role": "assistant", "content": long("并行调用两个工具"),
             "tool_calls": [{"id": "b1"}, {"id": "b2"}]},
            {"role": "tool", "tool_call_id": "b1", "content": long("第二组结果一")},
            {"role": "tool", "tool_call_id": "b2", "content": long("第二组结果二")},
            {"role": "user", "content": long("第三轮任务")},
            {"role": "assistant", "content": "收尾答复"},
        ]

    @staticmethod
    def _pairs_intact(msgs: list[dict]) -> bool:
        """校验成对形状(§9.1):带 tool_calls 的 assistant 紧跟数量与 id
        都匹配的 tool 行;tool 行要么紧跟其 assistant,要么紧跟同组 tool。"""
        for idx, m in enumerate(msgs):
            role = m.get("role")
            if role == "tool":
                prev = msgs[idx - 1] if idx else None
                ok = prev is not None and (
                    (prev.get("role") == "assistant" and prev.get("tool_calls"))
                    or prev.get("role") == "tool"
                )
                if not ok:
                    return False
            if role == "assistant" and m.get("tool_calls"):
                ids = [c["id"] for c in m["tool_calls"]]
                k = 0
                while idx + 1 + k < len(msgs) and msgs[idx + 1 + k].get("role") == "tool":
                    k += 1
                got = [msgs[idx + 1 + j].get("tool_call_id") for j in range(k)]
                if k != len(ids) or got != ids:
                    return False
        return True

    def test_prune_true_drops_tool_pairs_atomically(self) -> None:
        """prune=True 第二刀按组删(phase-42):任一带 tool_calls 的 assistant
        后面必须紧跟对应数量的 tool,不得出现孤立 tool 行。"""
        msgs = self._tool_pair_msgs()
        out = compress(msgs, budget=200, prune=True)
        assert len(out) < len(msgs)  # 确实发生了剪枝
        assert self._pairs_intact(out)
        ids_left = {m.get("tool_call_id") for m in out if m.get("role") == "tool"}
        calls_left = {
            c["id"] for m in out if m.get("role") == "assistant" for c in m.get("tool_calls", [])
        }
        assert ids_left == calls_left  # 没有缺对的任一侧
        assert "a1" not in ids_left  # 最旧的工具对被整组剪掉

    def test_prune_true_keeps_recent_tail(self) -> None:
        """剪到 len(out) <= 8 为止:最近的回合(含最后一组工具对)原样保留。"""
        msgs = self._tool_pair_msgs()
        out = compress(msgs, budget=200, prune=True)
        assert len(out) <= 8
        assert out[-1]["content"] == "收尾答复"  # 收尾回合仍在
        assert "第三轮任务" in out[-2]["content"]
        last_pair = next(m for m in reversed(out) if m.get("tool_calls"))
        idx = out.index(last_pair)
        assert [c["id"] for c in last_pair["tool_calls"]] == ["b1", "b2"]  # 最近一组完整
        assert [out[idx + 1]["tool_call_id"], out[idx + 2]["tool_call_id"]] == ["b1", "b2"]

    def test_prune_span_group_widths(self) -> None:
        """helper 的 span 宽度 >1 当且仅当删的是 assistant+tools 组(phase-42)。"""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "t"}]},
            {"role": "tool", "tool_call_id": "t", "content": "r"},
            {"role": "assistant", "content": "plain"},
            {"role": "tool", "tool_call_id": "x", "content": "orphan"},
        ]
        assert _prune_span(msgs, 0) == (1, 2)  # 跳过 system,单删 user
        assert _prune_span(msgs, 2) == (2, 4)  # assistant + tool 整组
        assert _prune_span(msgs, 4) == (4, 5)  # 无 tool_calls 的 assistant 单删
        assert _prune_span(msgs, 5) == (5, 6)  # 头部孤立 tool 单删
        assert _prune_span(msgs, 6) == (6, 6)  # 越界:无可剪对象


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
