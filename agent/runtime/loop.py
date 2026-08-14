"""事件循环(§9.1):取事件 → 分发 → 行动/沉默。

启动时先经游标补读离线期间的事件,再进入直推循环;handler 异常隔离,
不炸 loop(事件流是唯一全局设施,消费者必须最保守,§7.2/§7.10)。
"""

from __future__ import annotations

import fnmatch
import logging
from collections.abc import Awaitable, Callable

from platform_contracts import Event
from platform_eventbus import CursorStore, EventBus

Handler = Callable[[Event], Awaitable[None]]

log = logging.getLogger("agent.loop")


class EventLoop:
    def __init__(
        self,
        bus: EventBus,
        handlers: dict[str, Handler],
        *,
        cursors: CursorStore | None = None,
        subscriber: str = "agent.main",
    ) -> None:
        self._bus = bus
        self._handlers = handlers
        self._cursors = cursors
        self._subscriber = subscriber
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def _dispatch(self, event: Event) -> None:
        for pattern, handler in self._handlers.items():
            if fnmatch.fnmatchcase(event.type, pattern):
                try:
                    await handler(event)
                except Exception:  # 事件处理失败隔离,loop 继续
                    log.exception("事件处理失败: %s", event.type)

    async def run(self) -> None:
        if self._cursors is not None:
            for _seq, event in self._bus.read_missed(self._subscriber, self._cursors):
                await self._dispatch(event)
        sub = self._bus.subscribe(*self._handlers.keys())
        while not self._stopped:
            event = await sub.get()
            await self._dispatch(event)
            if self._cursors is not None and sub.last_seq:
                # 直推消费后推进游标:重启不重复消费已处理事件
                self._cursors.set(self._subscriber, sub.last_seq)
