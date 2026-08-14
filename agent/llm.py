"""LLM 客户端协议与测试用伪 LLM。

真实提供商接入在 services/llm(§8.8,演进第 4 步);本模块只定义协议。
FakeLLM 用于确定性测试与无 key 降级(§9.18)。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMReply:
    """一次 LLM 响应:要么最终文本,要么一组工具调用。"""

    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)

    @property
    def final(self) -> bool:
        return not self.tool_calls


class LLMClient(Protocol):
    async def complete(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None
    ) -> LLMReply: ...


ScriptFn = Callable[[list[dict[str, Any]], list[ToolSpec] | None], LLMReply]


class FakeLLM:
    """脚本化伪 LLM:依次弹出脚本;耗尽后返回默认文本;也可用函数动态生成。"""

    def __init__(
        self,
        script: list[LLMReply] | None = None,
        *,
        default: str = "收到。",
        dynamic: ScriptFn | None = None,
    ) -> None:
        self._script = list(script or [])
        self._default = default
        self._dynamic = dynamic
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None
    ) -> LLMReply:
        self.calls.append({"messages": messages, "tools": tools})
        if self._dynamic is not None:
            return self._dynamic(messages, tools)
        if self._script:
            return self._script.pop(0)
        return LLMReply(text=self._default)
