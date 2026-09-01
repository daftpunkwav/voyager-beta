"""事件循环(§9.1):取事件 → 分发 → 行动/沉默。

启动时先经游标补读离线期间的事件,再进入直推循环;handler 异常隔离,
不炸 loop(事件流是唯一全局设施,消费者必须最保守,§7.2/§7.10)。

订阅精确化(phase-28):只订 handlers 的 pattern + extra_patterns
(声明式 hook 声明过的领域事件),不订 "*";凡进入 loop 的事件都会
经 relay 转给 hook(独立熔断),无 relay 时等价空操作。
"""

from __future__ import annotations

import fnmatch
import logging
from collections.abc import Awaitable, Callable, Iterable

from platform_contracts import Event
from platform_eventbus import CursorStore, EventBus

from agent.runtime.recovery import CircuitBreaker, CircuitOpenError
from agent.runtime.trace import reset_current_trace, set_current_trace

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
        relay: Handler | None = None,
        extra_patterns: Iterable[str] = (),
    ) -> None:
        if "*" in handlers:
            raise ValueError('EventLoop handlers 禁止 "*":全量转发请用 relay')
        extra = tuple(extra_patterns)
        if "*" in extra:
            raise ValueError('EventLoop extra_patterns 禁止 "*":全量转发请用 relay')
        self._bus = bus
        self._handlers = handlers
        self._cursors = cursors
        self._subscriber = subscriber
        self._relay = relay
        self._relay_breaker = CircuitBreaker()  # relay 独立熔断:不拖垮领域 handler
        # 订阅 pattern:去重保序(handlers keys + hook 声明的领域事件类型)
        self._patterns = tuple(dict.fromkeys((*handlers.keys(), *extra)))
        self._stopped = False
        # 每 pattern 一把熔断(phase-12 §9.17):同一 handler 连续抛错达到
        # open_after 次后在 reset_after 内跳过,其余 pattern 不受影响,loop 不炸。
        # 不对 handler 做 with_retry:observe/consider 重试会重复 dispatch。
        self._breakers = {pattern: CircuitBreaker() for pattern in handlers}

    @property
    def patterns(self) -> tuple[str, ...]:
        """当前订阅 pattern(直推与补读共用同一元组)。"""
        return self._patterns

    def stop(self) -> None:
        self._stopped = True

    async def _dispatch(self, event: Event) -> None:
        # 事件 trace 放入 ContextVar:链内 capability 调用(deploy/bridge)自动同链(§7.8);
        # 处理完复位,避免污染 loop 任务上下文中的后续事件
        token = set_current_trace(event.trace_id) if event.trace_id else None
        try:
            for pattern, handler in self._handlers.items():
                if not fnmatch.fnmatchcase(event.type, pattern):
                    continue
                try:
                    await self._breakers[pattern].call(lambda h=handler: h(event))
                except CircuitOpenError:
                    log.warning(
                        "handler 连续失败已熔断,暂时跳过: %s (event=%s)", pattern, event.type
                    )
                except Exception:  # 事件处理失败隔离,loop 继续
                    log.exception("事件处理失败: %s", event.type)
            if self._relay is not None:
                # 凡进入 loop 的事件都 relay 给 hook(等同旧 "*" handler);
                # 熔断/异常只 skip relay,不影响上面已跑过的领域 handler
                try:
                    await self._relay_breaker.call(lambda: self._relay(event))
                except CircuitOpenError:
                    log.warning("relay 连续失败已熔断,暂时跳过 (event=%s)", event.type)
                except Exception:  # relay 失败隔离,loop 继续
                    log.exception("事件 relay 失败: %s", event.type)
        finally:
            if token is not None:
                reset_current_trace(token)

    async def run(self) -> None:
        if self._cursors is not None:
            # 补读与直推同 pattern:不再全表灌入,无关事件不进 agent(phase-28)
            for _seq, event in self._bus.read_missed(
                self._subscriber, self._cursors, types=self._patterns
            ):
                await self._dispatch(event)
        sub = self._bus.subscribe(*self._patterns)
        while not self._stopped:
            event = await sub.get()
            await self._dispatch(event)
            if self._cursors is not None and sub.last_seq:
                # 直推消费后推进游标:重启不重复消费已处理事件
                self._cursors.set(self._subscriber, sub.last_seq)
