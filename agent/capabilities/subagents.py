"""subagent 相关能力:列出、注册、急停。"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_subagents", description="已注册的 subagent 定义 + 运行中实例")
    def list_subagents() -> dict:
        return {
            "definitions": [
                {"name": d.name, "mode": d.mode, "description": d.description,
                 "persona": d.persona, "allowed_tools": list(d.allowed_tools)
                 if d.allowed_tools else None,
                 "max_rounds": d.max_rounds, "max_tool_calls": d.max_tool_calls,
                 "network_mode": d.network_mode}
                for d in deps.subagents.list()
            ],
            "running": [
                {
                    "id": i.id, "name": i.name, "status": i.status.value,
                    "goal": i.task.goal, "started_ts": i.state.started_ts,
                    "last_step": (
                        (i.state.steps[-1].summary or "")[:120]
                        if i.state.steps else ""
                    ),
                }
                for i in deps.spawner.instances.values()
            ],
        }

    @capability(reg, name="cancel_run", description="急停运行中的 subagent(按 id 或 name;'chat'=对话主实例)",
                cost=1)
    async def cancel_run(id_or_name: str) -> dict:
        """用户与 agent 都可急停(修复 Parity:原来双方都缺 kill switch)。"""
        cancelled = await deps.spawner.cancel(id_or_name)
        if not cancelled:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND,
                f"没有匹配的运行中实例: {id_or_name}",
                hint="list_subagents 查看运行中实例",
            )
        return {"cancelled": cancelled}

    @capability(reg, name="register_subagent", description="注册自建 subagent 定义",
                cost=2)
    def register_subagent(name: str, description: str, mode: str = "react",
                          allowed_tools: list[str] | None = None,
                          persona: str = "",
                          max_rounds: int | None = None,
                          max_tool_calls: int | None = None,
                          network_mode: str = "") -> dict:
        """写入 SubagentRegistry;mode 取七种模式枚举(非法值 AGENT.INVALID_INPUT)。

        allowed_tools 是能力面白名单裁剪(Toolbelt.trimmed,§9.4.1):
        不给 write_file 就是真的不能写,不是提示词约束;None = 不裁剪。
        max_rounds / max_tool_calls / network_mode 是权限档位覆盖(§9.9/§9.19):
        轮数不传跟随全局,网络档位空串继承全局;派出时只能比全局更严。
        """
        from agent.subagent.registry import SubagentDef

        d = SubagentDef(
            name=name, description=description, mode=mode, persona=persona,
            allowed_tools=tuple(allowed_tools) if allowed_tools else None,
            max_rounds=max_rounds, max_tool_calls=max_tool_calls,
            network_mode=network_mode or "",
        )
        deps.subagents.save(d)
        return {"name": d.name, "mode": d.mode, "allowed_tools": allowed_tools,
                "max_rounds": d.max_rounds, "max_tool_calls": d.max_tool_calls,
                "network_mode": d.network_mode}
