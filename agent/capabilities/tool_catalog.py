"""工具名册能力。"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_tools", description="当前工具面名册(自建 subagent 白名单候选项)")
    def list_tools() -> list[dict]:
        # 名册与 LLM 看到的 ToolSpec 一致(内部工具 + 领域桥 notes__* 等)
        return [{"name": s.name, "description": s.description}
                for s in deps.toolbelt.specs()]
