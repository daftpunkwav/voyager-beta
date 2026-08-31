"""spawn_subagent 工具:chat 实例经它派任务型 subagent(§9.4)。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent.tools.base import AgentTool

DispatchFn = Callable[..., Awaitable[Any]]  # master.dispatch_task


def spawn_tool(dispatch: DispatchFn) -> dict[str, AgentTool]:
    async def spawn_subagent(
        goal: str, persona: str = "", mode: str = "", name: str = ""
    ) -> dict:
        inst = await dispatch(
            goal, persona=persona, mode=mode or None, name=name
        )
        return {"subagent_id": inst.id, "name": inst.name, "status": inst.status.value}

    return {
        "spawn_subagent": AgentTool(
            name="spawn_subagent",
            description="派出 subagent 后台执行任务;完成后会主动通报结果",
            handler=spawn_subagent,
            schema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "persona": {"type": "string"},
                    "mode": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["goal"],
            },
            # 有副作用(创建运行实例):失败禁重试,防双实例(§9.17 写类不重试)
            write=True,
        )
    }
