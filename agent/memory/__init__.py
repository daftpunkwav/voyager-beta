"""记忆系统(§9.11):四类记忆 + 检索式查询门面(recall,§9.20 按需加载)。

保留策略(决策 §15):retention_days>0 时 purge 清理超期情节;0 = 交 agent 管理(不自动清)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.memory.episodic import EpisodicMemory
from agent.memory.profile import ProfileMemory
from agent.memory.semantic import SemanticMemory
from agent.memory.working import WorkingMemory


class Memory:
    def __init__(self, root: str | Path) -> None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.profile = ProfileMemory(root / "profile.db")
        self.episodic = EpisodicMemory(root / "episodic.db")
        self.semantic = SemanticMemory(root / "semantic.db")
        self.working = WorkingMemory()

    def recall(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """检索式注入:聚合画像/情节/语义三类命中,标注来源。"""
        hits: list[dict[str, Any]] = []
        for key, value in self.profile.all().items():
            if query in key or query in str(value):
                hits.append({"from": "profile", "key": key, "value": value})
        hits += [{"from": "episodic", **e} for e in self.episodic.search(query, limit)]
        hits += [
            {"from": "semantic", **f} for f in self.semantic.query(keyword=query, limit=limit)
        ]
        return hits[: max(limit * 2, 8)]

    def purge(self, retention_days: int) -> dict[str, int]:
        if retention_days <= 0:
            return {"episodic": 0}  # 交 agent 管理
        return {"episodic": self.episodic.purge(retention_days)}

    def close(self) -> None:
        self.profile.close()
        self.episodic.close()
        self.semantic.close()


__all__ = [
    "EpisodicMemory",
    "Memory",
    "ProfileMemory",
    "SemanticMemory",
    "WorkingMemory",
]
