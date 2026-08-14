"""联网工具(经网络权限层,§9.9 网络维)。

web_fetch 真实可用(httpx);web_search 是诚实的占位:搜索需外接搜索 MCP
或搜索提供商(§9.13),未接入前明确告知而不是假装搜过。
"""

from __future__ import annotations

from agent.tools.base import AgentTool

_MAX_CHARS = 12_000


def web_tools() -> dict[str, AgentTool]:
    async def web_fetch(url: str, max_chars: int = _MAX_CHARS) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            text = resp.text
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…[截断]"
        return f"HTTP {resp.status_code}\n{text}"

    def web_search(query: str) -> str:
        return (
            f"[未接入] 搜索({query})需要外接搜索 MCP 或搜索提供商;"
            "可在插件市场接入后用我重试(§9.13)"
        )

    return {
        "web_fetch": AgentTool(
            name="web_fetch",
            description="抓取网页内容(受网络白名单约束)",
            handler=web_fetch,
            dimension="network",
            schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
                "required": ["url"],
            },
        ),
        "web_search": AgentTool(
            name="web_search",
            description="联网搜索(当前未接入,调用会返回接入指引)",
            handler=web_search,
            dimension="network",
            schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
    }
