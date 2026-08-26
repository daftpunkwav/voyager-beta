"""注册表 → MCP server(stdio)。agent / 外部客户端经此消费 settings 能力。

运行:python -m services.settings.mcp_server(仓库根;需 pip install 'mcp>=1.0')
"""

from __future__ import annotations


def main():
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(Path(tempfile.gettempdir()) / "settings-mcp")
    return build_server(w.registry, name="settings")


if __name__ == "__main__":
    main()
