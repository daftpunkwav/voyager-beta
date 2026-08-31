"""摘要器(§9.6):维护 subagent 状态卡片。

master 默认只有"每个 subagent 在做什么"的卡片与基础信息;
subagent 自己持有任务全文上下文——上下文不直接共享,需要时经工具申请(§9.6)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Digest:
    subagent_id: str
    name: str
    goal: str
    status: str
    last_step: str = ""
    ts: float = field(default_factory=time.time)


class DigestStore:
    def __init__(self) -> None:
        self._cards: dict[str, Digest] = {}

    STEP_MAX = 120  # 与 agent.step SSE 截断一致

    def upsert(self, instance) -> Digest:
        """从 SubagentInstance 同步卡片(duck type,避免环依赖)。"""
        last = instance.state.steps[-1].summary if instance.state.steps else ""
        last = (last or "")[: self.STEP_MAX]
        card = Digest(
            subagent_id=instance.id,
            name=instance.name,
            goal=instance.task.goal,
            status=instance.status.value,
            last_step=last,
            ts=time.time(),
        )
        self._cards[instance.id] = card
        return card

    def remove(self, subagent_id: str) -> None:
        self._cards.pop(subagent_id, None)

    def list(self) -> list[Digest]:
        return sorted(self._cards.values(), key=lambda c: c.ts, reverse=True)

    def render(self) -> str:
        cards = self.list()
        if not cards:
            return ""
        lines = []
        for c in cards:
            tail = f" | 最近: {c.last_step}" if c.last_step else ""
            lines.append(f"- [{c.status}] {c.name}({c.subagent_id}): {c.goal}{tail}")
        return "\n".join(lines)
