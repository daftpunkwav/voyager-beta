"""注册表 → MCP server(§7.3 双协议生成之二)。

MCP SDK 为可选依赖(extra `mcp`),仅在 build_server 调用时导入。
build_tool_specs / dataclass_to_json_schema 为纯函数,无 SDK 也可用(供 REST 列能力复用)。
外部客户端的 OAuth 2.1 签发在后续步骤接入(§7.4);当前 default_actor 缺省为本地用户。
"""

from __future__ import annotations

import dataclasses
import json
import types
import typing
from typing import Any

from platform_contracts import LOCAL_USER, ActorRef

from platform_capability.registry import Registry

_PRIMITIVE_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}
_UNION_ORIGINS = {typing.Union, types.UnionType}  # Optional[X] 与 X | None


def _unwrap_optional(expected: Any) -> Any:
    """Optional[X] / X | None → X;其余原样返回。"""
    if typing.get_origin(expected) in _UNION_ORIGINS:
        args = [a for a in typing.get_args(expected) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return expected


def dataclass_to_json_schema(model: type) -> dict[str, Any]:
    """dataclass → JSON Schema(浅层:原始类型映射,复合类型标 object/array,其余 any)。"""
    hints = typing.get_type_hints(model)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in dataclasses.fields(model):
        expected = _unwrap_optional(hints.get(f.name))
        origin = typing.get_origin(expected)
        if expected in _PRIMITIVE_JSON:
            schema: dict[str, Any] = {"type": _PRIMITIVE_JSON[expected]}
        elif expected is list or origin is list:
            schema = {"type": "array"}
        elif expected is dict or origin is dict:
            schema = {"type": "object"}
        else:
            schema = {}
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)
        elif f.default is not dataclasses.MISSING:
            schema["default"] = f.default
        properties[f.name] = schema
    return {"type": "object", "properties": properties, "required": required}


def build_tool_specs(registry: Registry) -> list[dict[str, Any]]:
    """MCP tools/list 的工具描述(纯函数)。"""
    return [
        {
            "name": cap.name,
            "description": cap.description,
            "inputSchema": dataclass_to_json_schema(cap.input_model)
            if cap.input_model
            else {"type": "object", "properties": {}, "required": []},
        }
        for cap in registry.all()
    ]


def build_server(
    registry: Registry,
    *,
    name: str = "capability-server",
    default_actor: ActorRef = LOCAL_USER,
    auth: list | None = None,
    quota: list | None = None,
    audit: list | None = None,
):
    """把注册表生成为 MCP server(low-level Server,显式 schema)。SDK 缺失时抛 RuntimeError。"""
    try:
        from mcp.server import Server
        from mcp.types import ErrorData, McpError, TextContent, Tool
    except ImportError as exc:
        raise RuntimeError("build_server 需要 MCP SDK:pip install 'mcp>=1.0'") from exc

    from platform_actor import ActorContext
    from platform_contracts import ServiceError

    from platform_capability.guards import execute

    server: Any = Server(name)

    @server.list_tools()
    async def _list_tools() -> list:
        return [
            Tool(
                name=spec["name"],
                description=spec["description"],
                inputSchema=spec["inputSchema"],
            )
            for spec in build_tool_specs(registry)
        ]

    @server.call_tool()
    async def _call_tool(tool_name: str, arguments: dict) -> list:
        try:
            result = await execute(
                registry,
                tool_name,
                ActorContext(actor=default_actor),
                arguments or {},
                auth=auth,
                quota=quota,
                audit=audit,
            )
        except ServiceError as exc:
            raise McpError(
                ErrorData(code=-32000, message=json.dumps(exc.to_envelope(), ensure_ascii=False))
            ) from exc
        if dataclasses.is_dataclass(result) and not isinstance(result, type):
            result = dataclasses.asdict(result)
        elif hasattr(result, "to_dict"):
            result = result.to_dict()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return server
