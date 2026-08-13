"""测试用：把 StreamEvent / SSE 字符串拼成可断言的文本。"""
from __future__ import annotations

from typing import Any, Iterable

from agent_core.agents.stream_events import StreamEvent, encode_stream_item


def join_sse(chunks: Iterable[Any]) -> str:
    parts: list[str] = []
    for c in chunks:
        if isinstance(c, StreamEvent):
            parts.append(c.to_sse())
        elif isinstance(c, str):
            parts.append(encode_stream_item(c))
    return "\n".join(parts)
