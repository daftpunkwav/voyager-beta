"""注册表 → MCP server(stdio)。agent / 外部客户端经此消费 code-exec 能力。

运行:python -m services.code-exec.mcp_server(仓库根;需 pip install 'mcp>=1.0')
"""

from __future__ import annotations


def main():
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(
        Path(tempfile.gettempdir()) / "code-exec-mcp",
        workspace=Path(tempfile.gettempdir()) / "code-exec-workspace",
    )
    return build_server(w.registry, name="code-exec")


if __name__ == "__main__":
    main()
