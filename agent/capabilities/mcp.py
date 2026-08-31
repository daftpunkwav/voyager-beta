"""外接 MCP 相关能力:设置页添加 → 预览 → 批准挂载。"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.clients.pool import validate_server_config


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_mcp_servers",
                description="外接 MCP 配置与运行态(连接/错误/预览/已挂载)")
    def list_mcp_servers() -> list[dict]:
        return deps.mcp.list_state()

    @capability(reg, name="add_mcp_server",
                description="添加外接 MCP server(stdio 命令或 HTTP URL);先校验入库再试连预览",
                cost=1)
    async def add_mcp_server(id: str, kind: str, name: str = "", command: str = "",
                             args: list[str] | None = None, url: str = "",
                             approval: str = "item",
                             _actor: ActorRef = None) -> dict:
        cfg = validate_server_config({
            "id": id, "kind": kind, "name": name, "command": command,
            "args": args or [], "url": url, "approval": approval,
        })
        if deps.mcp.find_config(cfg["id"]) is not None:
            raise ServiceError("agent", ErrorSuffix.CONFLICT,
                               f"已存在同 id 的外接 MCP: {cfg['id']}")
        await deps.mcp.upsert_config({**cfg, "approved": []}, _actor)
        try:
            preview = await deps.mcp.preview(cfg["id"])
        except ServiceError as exc:
            # 连不上也保留配置:用户修好环境后可「刷新工具列表」重试,不吞半条配置
            return {"ok": True, "id": cfg["id"], "connected": False,
                    "error": str(exc), "preview": []}
        return {"ok": True, "id": cfg["id"], "connected": True, "error": "",
                "preview": preview}

    @capability(reg, name="preview_mcp_tools",
                description="对已配置的外接 MCP 再列一次工具(未批准也可预览)")
    async def preview_mcp_tools(id: str) -> dict:
        preview = await deps.mcp.preview(id)  # 失败抛 AGENT.UNAVAILABLE(可读消息)
        return {"id": id, "preview": preview}

    @capability(reg, name="approve_mcp_tools",
                description="批准外接 MCP 工具进对话工具面(整包 names=['*'] 或点名)",
                cost=1)
    async def approve_mcp_tools(id: str, names: list[str] | None = None,
                                _actor: ActorRef = None) -> dict:
        cfg = deps.mcp.find_config(id)
        if cfg is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND,
                               f"没有这台外接 MCP: {id}")
        prev = list(cfg.get("approved") or [])
        if names is None:
            if cfg.get("approval") != "package":
                raise ServiceError("agent", ErrorSuffix.INVALID_INPUT,
                                   "逐项批准需要给出 names;整包批准传 names=['*']")
            names = ["*"]
        if "*" in names or "*" in prev:
            approved = ["*"]  # 已整包批准过就保持整包,不悄悄收窄
        else:
            remote_names = {t.get("name") for t in await deps.mcp.preview(id)}
            unknown = [n for n in names if n not in remote_names]
            if unknown:
                raise ServiceError(
                    "agent", ErrorSuffix.INVALID_INPUT,
                    f"预览里没有这些工具: {', '.join(unknown)};"
                    "先「刷新工具列表」再批准",
                )
            # 逐项批准是累积(不撤销先前批准);撤销走移除整台 server
            approved = sorted(set(prev) | set(names))
        await deps.mcp.upsert_config({**cfg, "approved": approved}, _actor)
        mounted = deps.mcp.remount(id, approved)
        return {"ok": True, "id": id, "approved": approved, "mounted": mounted,
                "note": "已批准的工具进入工具名册;进行中的这轮对话看不到,"
                        "下一句或新对话可见。"}

    @capability(reg, name="remove_mcp_server",
                description="移除外接 MCP:断开、卸载其工具、删配置", cost=1)
    async def remove_mcp_server(id: str, _actor: ActorRef = None) -> dict:
        if deps.mcp.find_config(id) is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND,
                               f"没有这台外接 MCP: {id}")
        deps.mcp.unmount(id)
        await deps.mcp.drop_session(id)
        await deps.mcp.delete_config(id, _actor)
        return {"ok": True, "id": id}
