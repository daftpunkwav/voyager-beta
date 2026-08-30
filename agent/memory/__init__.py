"""记忆系统(§9.11):四类记忆 + 检索式查询门面(recall,§9.20 按需加载)。

保留策略(决策 §15):retention_days>0 时 purge 清理超期情节;0 = 交 agent 管理(不自动清)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

from agent.memory.episodic import EpisodicMemory
from agent.memory.profile import ProfileMemory
from agent.memory.semantic import SemanticMemory
from agent.memory.working import WorkingMemory

#: 可清空的记忆区(§10.11 设置页);"all" 表示全部
_ZONES = ("profile", "episodic", "semantic", "working")


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

    def clear(self, zone: str) -> dict[str, int]:
        """按区清空记忆(§10.11 设置页"查看/清空"),返回各区删除条数。

        与 purge 的保留策略语义无关:clear 是显式清库,purge 是按天惰性清理。
        """
        if zone == "all":
            targets = _ZONES
        elif zone in _ZONES:
            targets = (zone,)
        else:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"未知记忆区: {zone}",
                hint="zone 取值 profile / episodic / semantic / working / all",
            )
        out: dict[str, int] = {}
        for z in targets:
            if z == "profile":
                out[z] = self.profile.clear()
            elif z == "episodic":
                out[z] = self.episodic.clear()
            elif z == "semantic":
                out[z] = self.semantic.clear()
            else:
                out[z] = len(self.working)  # 清空前计数
                self.working.clear()
        return out

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
