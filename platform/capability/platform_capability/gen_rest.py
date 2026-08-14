"""注册表 → FastAPI router(§7.3 双协议生成之一)。

fastapi 为可选依赖(extra `rest`),仅在 build_router 调用时导入。
约定:GET {prefix} 列能力;POST {prefix}/{name} 以 JSON 对象调用;
JobRef → 202 Accepted;ServiceError → 统一错误体 + HTTP 映射(§7.10)。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from platform_actor import ActorContext, LocalTokenIssuer
from platform_contracts import LOCAL_USER, JobRef, ServiceError

from platform_capability.guards import AuditSink, CallRequest, execute
from platform_capability.registry import Registry


def _spec(cap) -> dict[str, Any]:
    from platform_capability.gen_mcp import dataclass_to_json_schema

    return {
        "name": cap.name,
        "description": cap.description,
        "cost": cap.cost,
        "reversible": cap.reversible,
        "scopes": sorted(cap.scopes),
        "long_running": cap.long_running,
        "input": dataclass_to_json_schema(cap.input_model) if cap.input_model else {},
    }


def build_router(
    registry: Registry,
    *,
    issuer: LocalTokenIssuer | None = None,
    auth: list[Callable[[CallRequest], None]] | None = None,
    quota: list[Callable[[CallRequest], None]] | None = None,
    audit: list[AuditSink | Callable] | None = None,
    prefix: str = "/capabilities",
):
    """把注册表生成为 FastAPI router。fastapi 未安装时抛 RuntimeError。"""
    try:
        from fastapi import APIRouter, Request
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise RuntimeError(
            "build_router 需要 fastapi:pip install 'platform-capability[rest]'"
        ) from exc

    # FastAPI 在路由注册时按模块命名空间解析注解字符串(本模块含
    # `from __future__ import annotations`),惰性导入的 Request 必须注入模块命名空间,
    # 否则 request 参数会被误当作 query 参数(422)。
    globals()["Request"] = Request

    router = APIRouter()

    @router.get(prefix)
    async def list_capabilities() -> dict[str, Any]:
        return {"capabilities": [_spec(c) for c in registry.all()]}

    @router.post(prefix + "/{name}")
    async def call_capability(name: str, request: Request):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001  # 解析失败统一按空对象处理,由入参校验报错
            body = {}
        try:
            if not isinstance(body, dict):
                from platform_contracts import ErrorSuffix

                raise ServiceError(
                    registry.domain, ErrorSuffix.INVALID_INPUT, "请求体必须是 JSON 对象"
                )
            ctx = _resolve_context(request, issuer)
            result = await execute(
                registry, name, ctx, body, auth=auth, quota=quota, audit=audit
            )
        except ServiceError as exc:
            return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())
        if isinstance(result, JobRef):
            return JSONResponse(status_code=202, content={"job": result.to_dict()})
        if dataclasses.is_dataclass(result) and not isinstance(result, type):
            result = dataclasses.asdict(result)
        return {"result": result}

    return router


def _resolve_context(request, issuer: LocalTokenIssuer | None) -> ActorContext:
    """Bearer 令牌 + issuer → 对应 actor;否则按本地单用户(§7.4)。"""
    header = request.headers.get("authorization", "")
    if issuer is not None and header.startswith("Bearer "):
        return ActorContext(actor=issuer.verify(header.removeprefix("Bearer ").strip()))
    return ActorContext(actor=LOCAL_USER)
