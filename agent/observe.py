"""Observe(§9.2):只读探查——看见用户在搬书,主动上前帮忙。

订阅领域事件,按规则产出"考虑事项"交给 master.consider;
默认只留痕不行动(自动行动由 agent.observe.auto_index 等设置开启)。
"""

from __future__ import annotations

import fnmatch
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from platform_contracts import Event

SuggestFn = Callable[[Event], str | None]
ConsiderFn = Callable[..., Awaitable[None]]  # (suggestion, *, source_event)


@dataclass(frozen=True)
class ObserveRule:
    pattern: str
    suggest: SuggestFn


def _source_ready(ev: Event) -> str | None:
    payload = ev.payload or {}
    name = payload.get("repo") or payload.get("title") or payload.get("source_id") or ""
    if not name:
        return None
    return f"用户导入了 {name} 且已解析完成。可考虑为其建立图谱索引。"


def default_rules() -> list[ObserveRule]:
    return [ObserveRule("source.ready", _source_ready)]


class Observer:
    def __init__(self, consider: ConsiderFn, rules: list[ObserveRule] | None = None) -> None:
        self._consider = consider
        self._rules = rules if rules is not None else default_rules()

    async def handle(self, event: Event) -> None:
        for rule in self._rules:
            if fnmatch.fnmatchcase(event.type, rule.pattern):
                suggestion = rule.suggest(event)
                if suggestion:
                    await self._consider(suggestion, source_event=event.type)
