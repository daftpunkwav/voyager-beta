"""MCP client 连接池(骨架,§9.13):外接 MCP 是 11b,本阶段只保证空池可查。

单体形态下领域工具经 deploy/bridge.py 的 capability 桥已进工具面,
**禁止**再用 MCP client 把同一批工具灌一遍;本池只装用户在设置页添加、
批准后的 stdio/URL MCP server(11b)。
"""

from __future__ import annotations


class McpClientPool:
    """外接 MCP server 的连接池。空池是合法稳态:没有外接 MCP 时一切照常。"""

    def list_servers(self) -> list[str]:
        """已连接(批准)的 server 名;本阶段恒为空。"""
        return []

    def list_tools(self, server: str) -> list[dict]:
        """某 server 暴露的 MCP tools;本阶段恒为空,不往 Toolbelt 塞工具。"""
        return []
