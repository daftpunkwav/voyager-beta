"""agent/clients:服务发现(discovery)+ MCP 连接池(pool)骨架。

见同目录 README.md;外接 MCP 产品化在 phase-11b。
"""

from agent.clients.discovery import discover_services
from agent.clients.pool import McpClientPool

__all__ = ["McpClientPool", "discover_services"]
