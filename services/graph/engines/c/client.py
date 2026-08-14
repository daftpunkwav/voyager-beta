"""C 引擎 sidecar 客户端(修订自旧 graph_engine_runtime/client.py)。

修订点:去掉对旧运行时上下文/错误码模块的依赖,错误统一 contracts.ServiceError;
只保留两条风味——sidecar RPC(同步 index)与原生引擎(POST /api/index + 轮询);
进程内引擎不再经本模块(回退逻辑在 engines/adapter.py)。
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import httpx
from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "graph"
EngineFlavor = Literal["sidecar_rpc", "native", "unknown"]


class CEngineClient:
    """C 引擎 sidecar 的 HTTP + JSON-RPC 客户端。base_url 空 = 未配置。"""

    def __init__(self, base_url: str, *, timeout: float = 300.0,
                 poll_interval: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._rpc_id = 0

    async def health(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/project-health")
                return resp.status_code == 200
        except Exception:  # noqa: BLE001  # 探测失败即不可用,由适配层回退
            return False

    async def call(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """JSON-RPC tools/call:search_graph / trace_path / get_graph_schema …"""
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0", "id": self._rpc_id, "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        }
        data = await self._post("/rpc", payload)
        if "error" in data:
            raise ServiceError(_DOMAIN, ErrorSuffix.INTERNAL,
                               f"C 引擎 RPC 错误: {data['error']}")
        return data.get("result")

    async def index_repository(self, repo_path: str, *, name: str | None = None,
                               mode: str = "moderate") -> dict[str, Any]:
        """原生索引:POST /api/index 后轮询 /api/index-status 到空闲。"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/index",
                json={"repo_path": repo_path, "name": name or "", "mode": mode},
            )
            if resp.status_code >= 400:
                raise ServiceError(_DOMAIN, ErrorSuffix.INTERNAL,
                                   f"C 引擎索引启动失败: HTTP {resp.status_code}")
            while True:
                await asyncio.sleep(self.poll_interval)
                st = await client.get(f"{self.base_url}/api/index-status")
                status = st.json()
                if not status.get("indexing", False):
                    if status.get("error"):
                        raise ServiceError(_DOMAIN, ErrorSuffix.INTERNAL,
                                           f"C 引擎索引失败: {status['error']}")
                    return {"project": name or repo_path, "status": "indexed",
                            "detail": status}

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        if not self.base_url:
            raise ServiceError(_DOMAIN, ErrorSuffix.UNAVAILABLE, "C 引擎未配置 base_url")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=payload)
        except httpx.HTTPError as exc:
            raise ServiceError(_DOMAIN, ErrorSuffix.UNAVAILABLE,
                               f"C 引擎不可达: {exc}") from exc
        if resp.status_code >= 400:
            raise ServiceError(_DOMAIN, ErrorSuffix.INTERNAL,
                               f"C 引擎 HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()
