"""注册表 → MCP server(stdio)。agent / 外部客户端经此消费本服务能力。

运行:python mcp_server.py(需 pip install 'mcp>=1.0';
stdio 装配方式以所用 MCP SDK 版本文档为准)
"""

from __future__ import annotations


def main():
    """构建并返回 MCP server;deps 注入与能力注册与 REST 入口一致。"""
    import asyncio
    import tempfile
    from pathlib import Path

    from capabilities import Deps, init_deps, registry
    from platform_capability import build_server
    from store import JobStore

    store = JobStore(Path(tempfile.gettempdir()) / "template-mcp.db")
    init_deps(Deps(store=store, bus=None, queue=asyncio.Queue()))
    return build_server(registry, name="template")


if __name__ == "__main__":
    main()
