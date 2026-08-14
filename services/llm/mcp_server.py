"""注册表 → MCP server(stdio)。agent / 外部客户端经此消费 llm 能力。"""

from __future__ import annotations


def main():
    import tempfile
    from pathlib import Path

    from capabilities import Deps, init_deps, registry
    from platform_capability import build_server
    from platform_secrets import SecretStore
    from store import ProviderStore

    data = Path(tempfile.gettempdir()) / "llm-mcp"
    init_deps(Deps(store=ProviderStore(data / "llm.db"),
                   secrets=SecretStore(data / "secrets.db")))
    return build_server(registry, name="llm")


if __name__ == "__main__":
    main()
