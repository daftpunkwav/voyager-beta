"""Typed Agent 流式事件 —— Hub/ReAct 与 HTTP SSE 之间的深 seam。

Hub / ReAct 产出 StreamEvent；agent_service 做落库副作用；
仅在 HTTP 边界调用 to_sse() 序列化。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StreamEventKind(StrEnum):
    TEXT_DELTA = "text_delta"
    THINKING = "thinking"
    AGENT_SWITCH = "agent_switch"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_THINKING = "subagent_thinking"
    SUBAGENT_TEXT = "subagent_text"
    SUBAGENT_DONE = "subagent_done"
    SELECT_REPOS = "select_repos"
    QUESTION = "question"
    DONE = "done"
    ERROR = "error"
    # 未知/扩展事件仍可承载，不强制进枚举时用 raw kind 字符串


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """领域流事件：kind + JSON 可序列化 payload。"""

    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """序列化为 SSE 帧（唯一 wire adapter）。"""
        return f"event: {self.kind}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"

    def __str__(self) -> str:
        """便于 join/日志；与 to_sse 等价。"""
        return self.to_sse()

    def __contains__(self, item: object) -> bool:
        """支持 `'event: x' in event` 的测试断言。"""
        return isinstance(item, str) and item in self.to_sse()

    @classmethod
    def from_sse(cls, chunk: str) -> StreamEvent | None:
        """解析 format_sse / to_sse 产出的单帧。"""
        if not isinstance(chunk, str) or not chunk.startswith("event: "):
            return None
        try:
            first_nl = chunk.find("\n")
            if first_nl < 0:
                return None
            kind = chunk[7:first_nl].strip()
            data_idx = chunk.find("data: ", first_nl)
            if data_idx < 0:
                return None
            payload = chunk[data_idx + 6 :].strip()
            if "\n" in payload:
                payload = payload.split("\n", 1)[0].strip()
            data = json.loads(payload)
            if not isinstance(data, dict):
                return None
            return cls(kind=kind, data=data)
        except Exception:
            return None

    @classmethod
    def coerce(cls, item: StreamEvent | str | Any) -> StreamEvent | None:
        """把 Hub 过渡期的 str/StreamEvent 统一成 StreamEvent。"""
        if isinstance(item, StreamEvent):
            return item
        if isinstance(item, str):
            return cls.from_sse(item)
        return None

    def is_kind(self, *kinds: str | StreamEventKind) -> bool:
        wanted = {str(k) for k in kinds}
        return self.kind in wanted


def format_sse(event: str, data: dict[str, Any]) -> StreamEvent:
    """构造 StreamEvent（保留旧名以降低迁移成本）。

    历史调用方把返回值当 str yield；请改为 yield event.to_sse()
    或直接 yield StreamEvent（由边界编码）。
    """
    return StreamEvent(kind=event, data=data)


def parse_sse_chunk(chunk: str) -> tuple[str, dict[str, Any]] | None:
    """兼容旧接口：返回 (kind, data)。"""
    ev = StreamEvent.from_sse(chunk)
    if ev is None:
        return None
    return ev.kind, ev.data


def encode_stream_item(item: StreamEvent | str) -> str:
    """HTTP StreamingResponse 边界：统一为 SSE 字符串。"""
    if isinstance(item, StreamEvent):
        return item.to_sse()
    return item
