"""发布/订阅:进程内 asyncio 队列直推 + 日志游标补读(§7.2)。

内存队列是加速通道,日志才是事实来源:订阅者掉队(队列满)只置 lagged 标记,
由 read_missed / replay 从日志补齐,不丢事件。
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field

from platform_contracts import Event

from platform_eventbus.cursor import CursorStore
from platform_eventbus.log import EventLog


@dataclass
class Subscription:
    """进程内订阅。lagged=True 表示有事件因队列满未直推,需 read_missed 补读。
    last_seq 记录已消费的最大 seq,供消费方推进游标(崩溃不重复消费)。"""

    patterns: tuple[str, ...]
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    lagged: bool = False
    last_seq: int = 0

    def matches(self, event_type: str) -> bool:
        return any(fnmatch.fnmatchcase(event_type, p) for p in self.patterns)

    async def get(self, timeout: float | None = None) -> Event:
        """取下一条直推事件。"""
        if timeout is None:
            seq, event = await self.queue.get()
        else:
            seq, event = await asyncio.wait_for(self.queue.get(), timeout)
        self.last_seq = seq
        return event


class EventBus:
    """进程内直推 + 持久化日志。跨进程消费方用 read_missed 持游标轮询。"""

    def __init__(self, log: EventLog, *, queue_size: int = 1000) -> None:
        self._log = log
        self._queue_size = queue_size
        self._subs: list[Subscription] = []

    @property
    def log(self) -> EventLog:
        return self._log

    async def publish(self, event: Event) -> int:
        """先落日志(事实来源),再直推进程内订阅者。返回 seq。"""
        seq = await asyncio.to_thread(self._log.append, event)
        for sub in self._subs:
            if not sub.matches(event.type):
                continue
            try:
                sub.queue.put_nowait((seq, event))
            except asyncio.QueueFull:
                sub.lagged = True
        return seq

    def subscribe(self, *patterns: str) -> Subscription:
        sub = Subscription(patterns=tuple(patterns), queue=asyncio.Queue(self._queue_size))
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    def replay(
        self, after_seq: int = 0, types: Iterable[str] | None = None, limit: int = 500
    ) -> list[tuple[int, Event]]:
        """从日志重放任意区间。"""
        return self._log.read_after(after_seq=after_seq, types=types, limit=limit)

    def read_missed(
        self,
        subscriber: str,
        cursors: CursorStore,
        types: Iterable[str] | None = None,
        limit: int = 500,
    ) -> list[tuple[int, Event]]:
        """游标补读:读 subscriber 游标之后的事件并推进游标。"""
        rows = self._log.read_after(after_seq=cursors.get(subscriber), types=types, limit=limit)
        if rows:
            cursors.set(subscriber, rows[-1][0])
        return rows
