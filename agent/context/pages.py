"""页面感知(§10.12 / §9.20):前端 provider 上报**摘要**,agent 按需取全文。

悬浮窗/chat 感知"用户在干什么":页面类型、条目数量、可见项标题、当前选中——
不是全量领域数据(服务侧 list 默认只回摘要,正文经 capability 按需取)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageSummary:
    page: str
    summary: str  # 如 "36 条笔记,当前打开《xxx》,指针在第 3 段"
    counts: dict[str, int] = field(default_factory=dict)
    selected: str = ""
    ts: float = field(default_factory=time.time)


class PageContextRegistry:
    def __init__(self) -> None:
        self._pages: dict[str, PageSummary] = {}
        self._current: str = ""

    def update(
        self,
        page: str,
        summary: str,
        *,
        counts: dict[str, int] | None = None,
        selected: str = "",
    ) -> PageSummary:
        item = PageSummary(page=page, summary=summary, counts=counts or {}, selected=selected)
        self._pages[page] = item
        self._current = page
        return item

    def current(self) -> PageSummary | None:
        return self._pages.get(self._current) if self._current else None

    def render(self) -> str:
        cur = self.current()
        if cur is None:
            return "(用户当前页面未知)"
        counts = ",".join(f"{k}={v}" for k, v in cur.counts.items())
        base = f"用户正在【{cur.page}】页:{cur.summary}"
        if counts:
            base += f"({counts})"
        if cur.selected:
            base += f";当前选中: {cur.selected}"
        return base
