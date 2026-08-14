"""skill 自动整理(§9.13):发现重复的工具调用序列 → 提议入库(L1 提示确认)。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from agent.memory.episodic import EpisodicMemory
from agent.tools.base import ConfirmFn

_TEMPLATE = "# {name}\n\n由重复流程自动整理(共出现 {count} 次)。\n\n## 步骤\n{steps}\n"


class SkillOrganizer:
    def __init__(
        self,
        episodic: EpisodicMemory,
        skills_dir: str | Path,
        *,
        confirm: ConfirmFn | None = None,
    ) -> None:
        self._episodic = episodic
        self._dir = Path(skills_dir)
        self._confirm = confirm

    def detect(self, *, min_count: int = 3, seq_len: int = 2) -> list[dict]:
        """在情节记忆的工具调用流里找重复出现的连续序列。"""
        entries = self._episodic.recent(limit=500, kind="tool")
        entries.reverse()  # 时间正序
        by_run: dict[str, list[str]] = {}
        for e in entries:
            by_run.setdefault(e["run_id"] or "_", []).append(e["summary"])
        grams: Counter[tuple[str, ...]] = Counter()
        for names in by_run.values():
            for i in range(len(names) - seq_len + 1):
                grams[tuple(names[i : i + seq_len])] += 1
        return [
            {"sequence": list(seq), "count": n}
            for seq, n in grams.most_common()
            if n >= min_count
        ]

    async def propose_and_save(
        self, *, min_count: int = 3, seq_len: int = 2
    ) -> list[Path]:
        """对每个重复模式:L1 提示用户确认(有确认通道时),确认后写 SKILL.md 草稿。"""
        saved: list[Path] = []
        for hit in self.detect(min_count=min_count, seq_len=seq_len):
            name = "auto-" + "-".join(hit["sequence"])[:40]
            if self._confirm is not None:
                ok = await self._confirm(
                    f"发现重复流程 {' → '.join(hit['sequence'])}(出现 {hit['count']} 次),"
                    "整理为 skill 入库吗?"
                )
                if not ok:
                    continue
            target = self._dir / name
            target.mkdir(parents=True, exist_ok=True)
            steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(hit["sequence"]))
            (target / "SKILL.md").write_text(
                _TEMPLATE.format(name=name, count=hit["count"], steps=steps),
                encoding="utf-8",
            )
            saved.append(target / "SKILL.md")
        return saved
