"""调用上下文(§7.4):跨服务调用沿链传递,任何环节不得提权。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from platform_contracts import ActorRef, new_trace_id

WILDCARD = "*"  # 全量 scope


@dataclass(frozen=True)
class ActorContext:
    """一次调用链上的行为者上下文。trace_id 贯穿一次交互的所有进程(§7.8)。"""

    actor: ActorRef
    trace_id: str = field(default_factory=new_trace_id)

    def has_scope(self, scope: str) -> bool:
        return WILDCARD in self.actor.scopes or scope in self.actor.scopes

    def restrict(self, scopes: Iterable[str]) -> ActorContext:
        """派生一个只会更窄的上下文:与请求范围取交集;持有 "*" 时收窄为请求范围。"""
        requested = set(scopes)
        if WILDCARD in self.actor.scopes:
            narrowed = tuple(sorted(requested))
        else:
            narrowed = tuple(sorted(set(self.actor.scopes) & requested))
        return ActorContext(actor=replace(self.actor, scopes=narrowed), trace_id=self.trace_id)
