"""健康监控:注册探针、按需/周期探测、状态变化发事件(§7.10)。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    Event,
    HealthReport,
    HealthStatus,
)
from platform_eventbus import EventBus

Probe = Callable[..., Any]  # () -> HealthReport | Awaitable[HealthReport]

_SYSTEM = ActorRef(kind=ActorKind.SYSTEM, id="platform.health")


class HealthMonitor:
    """服务健康监控。探针传输无关:可以打 HTTP /health,也可以是进程内检查。"""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._probes: dict[str, Probe] = {}
        self._last: dict[str, HealthReport] = {}
        self._task: asyncio.Task | None = None

    def register(self, service: str, probe: Probe) -> None:
        self._probes[service] = probe

    def unregister(self, service: str) -> None:
        self._probes.pop(service, None)
        self._last.pop(service, None)

    async def poll_once(self) -> dict[str, HealthReport]:
        """探测一轮;状态变化(含首次观测)发布 service.health.changed。"""
        for name, probe in self._probes.items():
            try:
                report = probe()
                if inspect.isawaitable(report):
                    report = await report
            except Exception as exc:  # noqa: BLE001  # 探针抛任何异常语义上都是 DOWN
                report = HealthReport(
                    service=name,
                    status=HealthStatus.DOWN,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            prev = self._last.get(name)
            self._last[name] = report
            if self._bus is not None and (prev is None or prev.status != report.status):
                await self._bus.publish(
                    Event(
                        type=DomainEvent.SERVICE_HEALTH_CHANGED,
                        actor=_SYSTEM,
                        payload={
                            "service": name,
                            "from": prev.status.value if prev else HealthStatus.UNKNOWN.value,
                            "to": report.status.value,
                            "detail": report.detail,
                            "ts": report.ts,
                        },
                    )
                )
        return dict(self._last)

    def start(self, interval: float = 5.0) -> None:
        """后台周期探测(gateway 用)。重复调用是幂等的:不泄漏旧任务。"""
        if self._task is not None and not self._task.done():
            return

        async def _run() -> None:
            while True:
                await self.poll_once()
                await asyncio.sleep(interval)

        self._task = asyncio.create_task(_run())

    async def stop(self) -> None:
        """取消并等待探测任务结束(清理在 stop 返回前完成)。"""
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def status(self, service: str) -> HealthStatus:
        report = self._last.get(service)
        return report.status if report else HealthStatus.UNKNOWN

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: report.to_dict() for name, report in self._last.items()}
