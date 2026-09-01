"""外接 MCP 工具挂载:把远端 tool 变成 AgentTool 挂进根 Toolbelt。

连接由 pool.py 负责;mount.py 只关心「工具名怎么定」「AgentTool 怎么造」
与「批准后 register / 移除时 unregister」。批准只是进名册的门;调用仍走
capability app 白名单维(dimension="app",target=工具名,与桥工具同一套
agent.app.allowed/denied,phase-31;见 §9.9/§9.13)。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from agent.clients.session import CALL_TIMEOUT, McpSession
from agent.tools.base import AgentTool, Toolbelt


def _tool_name(sid: str, remote_name: str) -> str:
    """远端工具名 → 本地工具面名字:mcp__<id>__<safe>。"""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", remote_name) or "tool"
    return f"mcp__{sid}__{safe}"


def _build_tool(cfg: dict, session: McpSession, remote: dict) -> AgentTool:
    """为一个远端 tool 构造 AgentTool;远端失败作为文本结果回给 LLM,不炸工具循环。"""
    remote_name = str(remote.get("name") or "")
    tool_name = _tool_name(cfg["id"], remote_name)

    async def handler(**kwargs: Any) -> str:
        try:
            return await asyncio.wait_for(
                session.call_tool(remote_name, kwargs), CALL_TIMEOUT
            )
        except Exception as exc:  # noqa: BLE001
            return f"[MCP 失败] {tool_name}: {exc}"

    schema = remote.get("schema") or remote.get("inputSchema") or {
        "type": "object",
        "additionalProperties": True,
    }
    return AgentTool(
        name=tool_name,
        # description 带展示名,模型能区分同名远端工具
        description=f"[MCP:{cfg['name']}] {remote.get('description') or remote_name}",
        handler=handler,
        schema=schema,
        # 批准只是进名册的门;调用走 app 维(target=工具名,同一套 agent.app.allowed)
        dimension="app",
    )


def unmount(toolbelt: Toolbelt | None, sid: str) -> list[str]:
    """从根名册卸掉 mcp__<sid>__*;返回实际卸载的名字。"""
    if toolbelt is None:
        return []
    prefix = f"mcp__{sid}__"
    names = [n for n in toolbelt.names() if n.startswith(prefix)]
    toolbelt.unregister(names)
    return names


def remount(
    toolbelt: Toolbelt | None,
    cfg: dict,
    session: McpSession | None,
    remote_tools: list[dict],
    approved: list[str],
) -> list[str]:
    """按 approved 挂载(["*"] = 全部 preview);先卸旧挂,避免残名。

    需要 preview 在场(先 preview());返回本次挂上的工具名。
    """
    if toolbelt is None:
        return []
    # 先卸旧挂:即使本次没有 session/preview,也不能留下残名(与拆分前一致)
    unmount(toolbelt, cfg["id"])
    if session is None or not remote_tools:
        return []
    if approved == ["*"]:
        selected = list(remote_tools)
    else:
        want = set(approved)
        selected = [t for t in remote_tools if t.get("name") in want]
    tools = {
        _tool_name(cfg["id"], str(t.get("name") or "")): _build_tool(cfg, session, t)
        for t in selected
    }
    toolbelt.register(tools)
    return sorted(tools)
