"""agent/clients:服务发现(discovery)+ 外接 MCP 连接池(pool/session)。

pool.py:外接 MCP 连接池(校验/连接,phase-11b);
mount.py:把远端 tool 变成 AgentTool 挂进根 Toolbelt(批准/挂载);
session.py:MCP 会话产品路径(stdio 子进程与 HTTP URL);
discovery.py:启动时按各服务 service.json 发现模块卡(只读卡,不连接)。

领域工具(notes__* 等)已走 deploy/bridge.py 的 capability 桥,
禁止再用 MCP client 把 services/*/mcp_server 灌进工具面。
"""

from agent.clients.discovery import discover_services
from agent.clients.pool import MCP_KEY, McpClientPool, validate_server_config
from agent.clients.session import McpSession

__all__ = [
    "MCP_KEY",
    "McpClientPool",
    "McpSession",
    "discover_services",
    "validate_server_config",
]
