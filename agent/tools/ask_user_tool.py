"""ask_user 的 LLM 工具形态(§9.15):出题/确认/选择/滑块。"""

from __future__ import annotations

from typing import Any

from agent.tools.ask_user import AskUser, Question
from agent.tools.base import AgentTool


def ask_user_tool(asker: AskUser) -> dict[str, AgentTool]:
    async def ask_user(
        prompt: str,
        kind: str = "confirm",
        options: list[str] | None = None,
        min: float | None = None,  # 与问题模型字段一致
        max: float | None = None,
    ) -> Any:
        answer = await asker.ask(
            Question(prompt=prompt, kind=kind, options=tuple(options or ()), min=min, max=max)
        )
        return answer if answer is not None else "(用户超时未答)"

    return {
        "ask_user": AgentTool(
            name="ask_user",
            description="向用户提问:confirm 确认 / choice 选择 / slider 滑块 / text 填空;可用来出题",
            handler=ask_user,
            schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "kind": {"type": "string", "enum": ["confirm", "choice", "slider", "text"]},
                    "options": {"type": "array"},
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                },
                "required": ["prompt"],
            },
        )
    }
