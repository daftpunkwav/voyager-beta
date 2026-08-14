"""request_context 工具:subagent 向 master 申请额外上下文(§9.6)。

上下文不直接共享:subagent 持有自己任务的上下文;需要更广上下文(用户画像、
其他 subagent 在做什么)时,经本工具向 master 申请,master 侧只给摘要。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.tools.base import AgentTool

ContextProvider = Callable[[str], dict[str, Any]]  # (申请理由) → 摘要字典


def request_context_tool(provider: ContextProvider) -> dict[str, AgentTool]:
    def request_context(need: str) -> dict:
        return provider(need)

    return {
        "request_context": AgentTool(
            name="request_context",
            description="向主 agent 申请额外上下文(用户画像/其他 subagent 状态等),说明用途",
            handler=request_context,
            schema={
                "type": "object",
                "properties": {"need": {"type": "string"}},
                "required": ["need"],
            },
        )
    }
