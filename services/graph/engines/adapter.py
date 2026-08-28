"""引擎适配层(§8.4):默认 C 引擎,不可用自动回退 Python 引擎并发事件告知。

- 用户可在设置里强制(graph.engine.mode = auto / c / python,决策 §15);
- 适配层对两条管线屏蔽引擎差异(统一 call/health/index 形态);
- 回退发生一次即记录,event `graph.engine.fallback` 让前端引擎徽章显示降级态。
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Protocol

from platform_contracts import ActorKind, ActorRef, Event
from platform_eventbus import EventBus

from .c.client import CEngineClient

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="graph.engine")


class Engine(Protocol):
    async def health(self) -> bool: ...
    async def call(self, name: str, args: dict[str, Any]) -> Any: ...
    async def index_repository(self, repo_path: str, **kw: Any) -> dict[str, Any]: ...


class _PythonEngineAdapter:
    """把进程内 Python 引擎(同步 call)包成与 C 客户端一致的异步形态。"""

    flavor = "python"

    def __init__(self, data_root: Any) -> None:
        from .python.engine import GraphEngine
        self._engine = GraphEngine(data_root)

    async def health(self) -> bool:
        return bool(self._engine.health())

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        # 搜索/导出含磁盘与 CPU,不得占事件循环
        return await asyncio.to_thread(self._engine.call, name, args)

    async def index_repository(self, repo_path: str, **kw: Any) -> dict[str, Any]:
        return await asyncio.to_thread(partial(
            self._engine.index_repository,
            repo_path, mode=kw.get("mode", "moderate"), name=kw.get("name"),
        ))


class EngineAdapter:
    """引擎选择与回退(§8.4)。resolve() 幂等:每次调用先按设置探测。"""

    def __init__(self, *, c_base_url: str, python_data_root: Any,
                 bus: EventBus | None = None, mode: str = "auto") -> None:
        self._c = CEngineClient(c_base_url) if c_base_url else None
        self._python = _PythonEngineAdapter(python_data_root)
        self._bus = bus
        self._mode = mode  # auto | c | python

    async def resolve(self) -> tuple[Engine, str]:
        """返回 (引擎, 引擎名)。auto:C 健康则 C,否则回退 Python 并发事件。"""
        if self._mode == "python":
            return self._python, "python"
        if self._c is not None and await self._c.health():
            return self._c, "c"  # type: ignore[return-value]
        if self._mode == "c":
            from platform_contracts import ErrorSuffix, ServiceError
            raise ServiceError(
                "graph", ErrorSuffix.UNAVAILABLE,
                "已强制 C 引擎但 C 引擎不可达",
                hint="检查 sidecar 进程;或把 graph.engine.mode 改为 auto",
            )
        await self._emit("graph.engine.fallback",
                         reason="C 引擎不可达,已回退 Python 引擎")
        return self._python, "python"

    async def _emit(self, type_: str, **payload) -> None:
        if self._bus is not None:
            await self._bus.publish(Event(type=type_, actor=_ACTOR, payload=payload))
