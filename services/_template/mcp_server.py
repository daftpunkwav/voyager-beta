"""注册表 → MCP server(stdio)。agent / 外部客户端经此消费本服务能力。

运行:python -m services._template.mcp_server(仓库根;需 pip install 'mcp>=1.0';
stdio 装配方式以所用 MCP SDK 版本文档为准)
"""

from __future__ import annotations


def main():
    """构建并返回 MCP server;接线与 REST 入口共用 wiring.py。"""
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(Path(tempfile.gettempdir()) / "template-mcp")
    return build_server(w.registry, name="template")


if __name__ == "__main__":
    main()
