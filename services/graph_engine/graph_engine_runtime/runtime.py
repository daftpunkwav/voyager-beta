"""Graph Runtime Interface + Embedded 实现。

api_backend 只依赖 GraphRuntimeInterface；EmbeddedGraphRuntime 在启动期
注入 GraphRuntimeContext（settings / DB 工厂 / GitHub token / AppState 服务），
进程内 delegate 到 client / index_pipeline / sidecar。
"""
from __future__ import annotations

from typing import Any, Protocol

from graph_engine_runtime import index_pipeline, sidecar
from graph_engine_runtime.client import GraphEngineClient
from graph_engine_runtime.context import (
    GraphRuntimeContext,
    set_runtime_context,
)


class GraphRuntimeInterface(Protocol):
    """Graph 引擎统一接口（api_backend / agent_core 只依赖此接口）。"""

    # —— 引擎访问（C sidecar 优先，Python graph_fallback 回退） ——
    async def health(self) -> bool: ...
    async def fetch_layout(self, project: str, **kwargs: Any) -> dict[str, Any]: ...
    async def index_repository(self, repo_path: str, **kwargs: Any) -> Any: ...
    async def search_graph(self, project: str, **kwargs: Any) -> Any: ...
    async def trace_path(self, project: str, **kwargs: Any) -> Any: ...
    async def drop_project(self, project: str) -> Any: ...
    async def list_cross_edges(self) -> list[dict[str, Any]]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any: ...

    # —— 索引 job 状态机 ——
    async def trigger_index(self, db: Any, project_id: Any, **kwargs: Any) -> dict: ...
    async def cancel_index(self, db: Any, project_id: Any) -> dict: ...
    async def delete_index(self, db: Any, project_id: Any) -> dict: ...
    async def get_status_out(self, db: Any, project_id: Any) -> dict: ...
    async def list_index_statuses(self, db: Any) -> list[dict]: ...

    # —— 生命周期（EmbeddedGraphRuntime 由 api_backend lifespan 代理调用） ——
    async def start_worker(self) -> None: ...
    async def stop_worker(self) -> None: ...


class EmbeddedGraphRuntime:
    """Embedded 实现（默认，同进程）。由 api_backend 构造并注入依赖。"""

    def __init__(
        self,
        context: GraphRuntimeContext,
        *,
        auto_start_sidecar: bool = True,
    ):
        set_runtime_context(context)
        self._ctx = context
        self._auto_start_sidecar = auto_start_sidecar
        # 单例 client：GraphEngineClient 的 flavor 探测结果缓存在实例内，
        # 每次 new 会让 _flavor 缓存失效、每个请求重做最多 3 次 HTTP 探测
        self._client = GraphEngineClient()

    # —— 引擎访问（透传 GraphEngineClient 单例） ——
    async def health(self) -> bool:
        return await self._client.health()

    async def fetch_layout(self, project: str, **kwargs: Any) -> dict[str, Any]:
        return await self._client.fetch_layout(project, **kwargs)

    async def index_repository(self, repo_path: str, **kwargs: Any) -> Any:
        return await self._client.index_repository(repo_path, **kwargs)

    async def search_graph(self, project: str, **kwargs: Any) -> Any:
        return await self._client.search_graph(project, **kwargs)

    async def trace_path(self, project: str, **kwargs: Any) -> Any:
        return await self._client.trace_path(project, **kwargs)

    async def drop_project(self, project: str) -> Any:
        return await self._client.drop_project(project)

    async def list_cross_edges(self) -> list[dict[str, Any]]:
        return await self._client.list_cross_edges()

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return await self._client.call_tool(name, arguments)

    # —— 索引 job 状态机（透传 index_pipeline） ——
    async def trigger_index(self, db: Any, project_id: Any, **kwargs: Any) -> dict:
        return await index_pipeline.trigger_index(db, project_id, **kwargs)

    async def cancel_index(self, db: Any, project_id: Any) -> dict:
        return await index_pipeline.cancel_index(db, project_id)

    async def delete_index(self, db: Any, project_id: Any) -> dict:
        return await index_pipeline.delete_index(db, project_id)

    async def get_status_out(self, db: Any, project_id: Any) -> dict:
        return await index_pipeline.get_status_out(db, project_id)

    async def list_index_statuses(self, db: Any) -> list[dict]:
        return await index_pipeline.list_index_statuses(db)

    # —— 生命周期 ——
    async def start_worker(self) -> None:
        """拉起 C sidecar（可选）并启动常驻索引 worker 池。"""
        settings = self._ctx.settings
        if self._auto_start_sidecar and settings.graph_auto_start and (
            (settings.graph_engine_url or "").strip()
        ):
            try:
                await sidecar.ensure_graph_engine_sidecar()
            except Exception:
                pass
        await index_pipeline.start_index_worker()

    async def stop_worker(self) -> None:
        await index_pipeline.stop_index_worker()
        try:
            await sidecar.stop_graph_engine_sidecar()
        except Exception:
            pass
