"""按需加载器(§9.20):索引常驻,全文按需;每次加载计入(加载入审计)。"""

from __future__ import annotations

import time
from typing import Any


class OnDemandLoader:
    """skill 全文 / 记忆检索 / 页面上下文的统一按需入口。"""

    def __init__(
        self,
        *,
        skills: Any = None,  # SkillLoader
        memory: Any = None,  # Memory
        pages: Any = None,  # PageContextRegistry
    ) -> None:
        self._skills = skills
        self._memory = memory
        self._pages = pages
        self.loads: list[dict[str, Any]] = []  # (kind, key, ts) 加载留痕

    def _record(self, kind: str, key: str) -> None:
        self.loads.append({"kind": kind, "key": key, "ts": time.time()})

    def skill_text(self, name: str) -> str:
        self._record("skill", name)
        if self._skills is None:
            return "[skill 体系未装配]"
        return self._skills.full_text(name)

    def recall(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        self._record("memory", query)
        if self._memory is None:
            return []
        return self._memory.recall(query, limit)

    def page_summary(self) -> str:
        self._record("page", "current")
        if self._pages is None:
            return "(页面感知未装配)"
        return self._pages.render()
