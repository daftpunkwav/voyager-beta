"""
Voyager 图谱客户端。

优先连接 `GRAPH_ENGINE_URL` 指向的本仓 C 引擎 sidecar（`services/graph_engine/graph_engine_core`）；
未配置或 sidecar 不健康时回退进程内 Python `graph_fallback.GraphEngine`。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from py_shared import error_codes as EC

from graph_engine_runtime.context import get_runtime_context

logger = logging.getLogger(__name__)

EngineFlavor = Literal["native", "fallback", "unknown"]


class GraphEngineError(Exception):
    def __init__(self, message: str, *, code: str = EC.GRAPH_QUERY_FAILED):
        super().__init__(message)
        self.message = message
        self.code = code


def _local_engine():
    from graph_fallback import get_engine

    settings = get_runtime_context().settings
    root = settings.graph_allowed_root
    return get_engine(data_root=root)


def _unwrap_mcp_result(result: Any) -> Any:
    """解析 引擎/MCP tools/call 的 content / structuredContent。"""
    if not isinstance(result, dict):
        return result
    if result.get("isError"):
        msg = "引擎工具错误"
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("text"):
                msg = str(first["text"])
        raise GraphEngineError(msg, code=EC.GRAPH_QUERY_FAILED)
    structured = result.get("structuredContent")
    if structured is not None:
        return structured
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and "text" in first:
            text = first.get("text") or ""
            try:
                return json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return {"text": text}
    return result


def _norm_path(path: str) -> str:
    return str(Path(path).resolve()).replace("\\", "/").rstrip("/").lower()


class GraphEngineClient:
    """统一引擎端口：sidecar（原生 C / graph_fallback）或进程内引擎。"""

    def __init__(self, base_url: str | None = None, timeout: float = 300.0):
        settings = get_runtime_context().settings
        url = base_url
        if url is None:
            url = settings.graph_engine_url
        self.base_url = (url or "").rstrip("/")
        self.timeout = timeout
        self._rpc_id = 0
        self._flavor: EngineFlavor | None = None

    async def health(self) -> bool:
        if self.base_url:
            return await self._sidecar_ok()
        try:
            return bool(_local_engine().health())
        except Exception as exc:
            logger.warning("自研图谱引擎不可用: %s", exc)
            return False

    async def flavor(self) -> EngineFlavor:
        if not self.base_url:
            return "unknown"
        if self._flavor is None:
            await self._sidecar_ok()
        return self._flavor or "unknown"

    async def fetch_layout(
        self,
        project: str,
        *,
        max_nodes: int = 5000,
        graph: str = "code",
    ) -> dict[str, Any]:
        if self.base_url and await self._sidecar_ok():
            params = {"project": project, "max_nodes": str(max_nodes)}
            # 自研 sidecar 兼容 graph 参数；原生引擎忽略未知 query
            if await self.flavor() != "native":
                params["graph"] = graph
            return await self._http_get("/api/layout", params)
        try:
            return await asyncio.to_thread(
                _local_engine().fetch_layout,
                project,
                max_nodes=max_nodes,
                graph=graph,
            )
        except Exception as exc:
            raise GraphEngineError(
                f"读取布局失败：{exc}", code=EC.GRAPH_QUERY_FAILED
            ) from exc

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        if self.base_url and await self._sidecar_ok():
            if name == "index_repository":
                return await self.index_repository(
                    args.get("repo_path") or ".",
                    mode=args.get("mode") or "moderate",
                    name=args.get("name"),
                    target_projects=args.get("target_projects"),
                    persistence=bool(args.get("persistence", True)),
                )
            if name == "drop_project":
                return await self.drop_project(
                    args.get("project") or args.get("name") or ""
                )
            return await self._http_rpc(name, args)

        eng = _local_engine()

        def _sync_call() -> Any:
            # 统一经 GraphEngine.call 分发（与 HTTP server._dispatch 共用同一映射）
            return eng.call(name, args)

        try:
            return await asyncio.to_thread(_sync_call)
        except GraphEngineError:
            raise
        except Exception as exc:
            raise GraphEngineError(str(exc), code=EC.GRAPH_QUERY_FAILED) from exc

    async def index_repository(
        self,
        repo_path: str,
        *,
        mode: str = "moderate",
        name: Optional[str] = None,
        target_projects: list[str] | None = None,
        persistence: bool = True,
        should_abandon: Any = None,
    ) -> Any:
        """本地引擎可传 should_abandon；原生 sidecar 通过轮询 index-status 检查放弃。"""
        if self.base_url and await self._sidecar_ok():
            flavor = await self.flavor()
            if flavor == "native":
                return await self._native_index(
                    repo_path,
                    name=name,
                    should_abandon=should_abandon,
                )
            # 自研 sidecar：RPC 同步 index（支持 mode）
            return await self._http_rpc(
                "index_repository",
                {
                    "repo_path": repo_path,
                    "mode": mode,
                    "name": name,
                    "target_projects": target_projects,
                    "persistence": persistence,
                },
            )

        eng = _local_engine()

        def _sync() -> Any:
            return eng.index_repository(
                repo_path,
                mode=mode,
                name=name,
                target_projects=target_projects,
                persistence=persistence,
                should_abandon=should_abandon,
            )

        try:
            return await asyncio.to_thread(_sync)
        except GraphEngineError:
            raise
        except Exception as exc:
            raise GraphEngineError(str(exc), code=EC.GRAPH_QUERY_FAILED) from exc

    async def _native_index(
        self,
        repo_path: str,
        *,
        name: Optional[str],
        should_abandon: Any,
    ) -> dict[str, Any]:
        """原生引擎 UI：POST /api/index + 轮询 /api/index-status。

        注意：原生 UI 的 /rpc index_repository 已禁用；mode 由 C 引擎默认管线决定
        （等价于 full/LSP，质量高于自研 Python 索引）。
        """
        root = str(Path(repo_path).resolve()).replace("\\", "/")
        payload: dict[str, Any] = {"root_path": root}
        if name:
            payload["project_name"] = name

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.base_url}/api/index", json=payload)
        except Exception as exc:
            raise GraphEngineError(
                f"原生引擎启动索引失败：{exc}", code=EC.GRAPH_ENGINE_UNAVAILABLE
            ) from exc

        if resp.status_code not in (200, 202):
            raise GraphEngineError(
                f"原生引擎索引拒绝 HTTP {resp.status_code}：{resp.text[:300]}",
                code=EC.GRAPH_INDEX_FAILED,
            )

        want = _norm_path(root)
        deadline = time.monotonic() + max(self.timeout, 60.0)
        last_error = ""

        while time.monotonic() < deadline:
            if callable(should_abandon) and should_abandon():
                return {"abandoned": True, "project": name or root}

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    st = await client.get(f"{self.base_url}/api/index-status")
                    jobs = st.json() if st.status_code == 200 else []
            except Exception:
                jobs = []

            matched = None
            if isinstance(jobs, list):
                for job in jobs:
                    if not isinstance(job, dict):
                        continue
                    jpath = _norm_path(str(job.get("path") or ""))
                    if jpath == want:
                        matched = job
                        break

            if matched is not None:
                status = str(matched.get("status") or "")
                if status == "done":
                    break
                if status == "error":
                    last_error = str(matched.get("error") or "原生引擎索引失败")
                    raise GraphEngineError(last_error, code=EC.GRAPH_INDEX_FAILED)
            elif jobs == []:
                # 槽位已清空：用 project-health 确认是否已落库
                proj = (name or "").strip()
                if proj:
                    health = await self._project_health(proj)
                    if health.get("status") == "healthy":
                        break

            await asyncio.sleep(1.5)
        else:
            raise GraphEngineError(
                f"原生引擎索引超时（>{int(self.timeout)}s）",
                code=EC.GRAPH_INDEX_FAILED,
            )

        proj = (name or "").strip()
        out: dict[str, Any] = {"ok": True, "project": proj or root, "engine": "native"}
        if proj:
            health = await self._project_health(proj)
            if health.get("status") == "healthy":
                out["nodes"] = health.get("nodes")
                out["edges"] = health.get("edges")
        return out

    async def _project_health(self, project: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/api/project-health",
                    params={"name": project},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data if isinstance(data, dict) else {}
        except Exception:
            logger.debug("project-health 查询失败 project=%s", project, exc_info=True)
        return {}

    async def search_graph(self, project: str, **kwargs: Any) -> Any:
        return await self.call_tool(
            "search_graph", {"project": project, **kwargs}
        )

    async def search_code(self, project: str, **kwargs: Any) -> Any:
        return await self.call_tool("search_code", {"project": project, **kwargs})

    async def trace_path(self, project: str, **kwargs: Any) -> Any:
        """对齐原生引擎：优先 function_name；兼容本地引擎的 symbol/start。"""
        args = {"project": project, **kwargs}
        if "function_name" not in args:
            sym = args.pop("symbol", None) or args.pop("start", None)
            if sym:
                args["function_name"] = sym
        if "mode" not in args and ("kind" in args or "type" in args):
            kind = args.pop("kind", None) or args.pop("type", None)
            if kind in ("calls", "data_flow", "cross_service"):
                args["mode"] = kind
            elif kind == "data":
                args["mode"] = "data_flow"
        return await self.call_tool("trace_path", args)

    async def get_architecture(self, project: str, aspects: list[str] | None = None) -> Any:
        args: dict[str, Any] = {"project": project}
        if aspects:
            args["aspects"] = aspects
        return await self.call_tool("get_architecture", args)

    async def get_code_snippet(self, project: str, qualified_name: str) -> Any:
        return await self.call_tool(
            "get_code_snippet",
            {"project": project, "qualified_name": qualified_name},
        )

    async def get_graph_schema(self, project: str) -> Any:
        return await self.call_tool("get_graph_schema", {"project": project})

    async def drop_project(self, project: str) -> Any:
        """删除引擎侧图谱。原生引擎：DELETE /api/project；自研：RPC/本地 drop_project。"""
        name = (project or "").strip()
        if not name:
            raise GraphEngineError("缺少 project 名称", code=EC.GRAPH_QUERY_FAILED)
        if self.base_url and await self._sidecar_ok():
            if await self.flavor() == "native":
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        # name 可能含特殊字符，走 query
                        resp = await client.request(
                            "DELETE",
                            f"{self.base_url}/api/project",
                            params={"name": name},
                        )
                        if resp.status_code == 200:
                            return resp.json() if resp.content else {"deleted": True}
                        raise GraphEngineError(
                            f"原生引擎删除项目失败 HTTP {resp.status_code}：{resp.text[:200]}",
                            code=EC.GRAPH_QUERY_FAILED,
                        )
                except GraphEngineError:
                    raise
                except Exception as exc:
                    raise GraphEngineError(
                        f"原生引擎删除项目失败：{exc}", code=EC.GRAPH_ENGINE_UNAVAILABLE
                    ) from exc
            return await self._http_rpc("drop_project", {"project": name})
        return await asyncio.to_thread(_local_engine().drop_project, name)

    async def query_graph(self, project: str, query: str, **kwargs: Any) -> Any:
        return await self.call_tool(
            "query_graph", {"project": project, "query": query, **kwargs}
        )

    async def list_cross_edges(self) -> list[dict[str, Any]]:
        if self.base_url and await self._sidecar_ok():
            if await self.flavor() == "native":
                # 原生引擎 UI 无此路由；跨仓边由引擎内部维护
                return []
            data = await self._http_get("/api/cross-edges", {})
            return data.get("edges") or []
        return await asyncio.to_thread(_local_engine().list_cross_edges)

    async def _sidecar_ok(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                # 原生引擎 UI：无 /health，用 /api/ui-config
                try:
                    resp = await client.get(f"{self.base_url}/api/ui-config")
                    if resp.status_code == 200:
                        self._flavor = "native"
                        return True
                except Exception:
                    pass
                # 自研 graph_fallback.server
                try:
                    resp = await client.get(f"{self.base_url}/health")
                    if resp.status_code == 200:
                        self._flavor = "fallback"
                        return True
                except Exception:
                    pass
                # 兜底：RPC tools/list
                try:
                    resp = await client.post(
                        f"{self.base_url}/rpc",
                        json={
                            "jsonrpc": "2.0",
                            "id": 0,
                            "method": "tools/list",
                            "params": {},
                        },
                    )
                    if resp.status_code == 200:
                        self._flavor = self._flavor or "unknown"
                        return True
                except Exception:
                    pass
        except Exception:
            return False
        return False

    async def _http_get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}{path}", params=params)
                if resp.status_code != 200:
                    raise GraphEngineError(
                        f"引擎 HTTP {resp.status_code}：{resp.text[:300]}",
                        code=EC.GRAPH_QUERY_FAILED,
                    )
                data = resp.json()
                return data if isinstance(data, dict) else {"result": data}
        except GraphEngineError:
            raise
        except Exception as exc:
            raise GraphEngineError(
                f"引擎请求失败：{exc}", code=EC.GRAPH_ENGINE_UNAVAILABLE
            ) from exc

    async def _http_rpc(self, name: str, arguments: dict[str, Any]) -> Any:
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/rpc", json=payload)
                if resp.status_code != 200:
                    raise GraphEngineError(
                        f"引擎 rpc HTTP {resp.status_code}",
                        code=EC.GRAPH_QUERY_FAILED,
                    )
                data = resp.json()
        except GraphEngineError:
            raise
        except Exception as exc:
            raise GraphEngineError(
                f"引擎 rpc 失败：{exc}", code=EC.GRAPH_ENGINE_UNAVAILABLE
            ) from exc
        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise GraphEngineError(msg or "引擎错误", code=EC.GRAPH_QUERY_FAILED)
        result = data.get("result") if isinstance(data, dict) else data
        return _unwrap_mcp_result(result)
