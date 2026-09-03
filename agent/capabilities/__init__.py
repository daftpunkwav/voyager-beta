"""agent 能力注册包(§5)。

按业务拆分子文件,最终注册到同一张 Registry。公开入口保持不变:
    from agent.capabilities import CapabilityDeps, build_agent_registry
"""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities import (
    ask,
    mcp,
    memory,
    pages,
    personas,
    plugins,
    resource,
    settings,
    skills,
    subagents,
    tool_catalog,
    user_hooks,
)
from agent.capabilities.deps import CapabilityDeps


def build_agent_registry(deps: CapabilityDeps) -> Registry:
    reg = Registry("agent")
    settings.register(reg, deps)
    resource.register(reg, deps)
    skills.register(reg, deps)
    subagents.register(reg, deps)
    personas.register(reg, deps)
    tool_catalog.register(reg, deps)
    mcp.register(reg, deps)
    plugins.register(reg, deps)
    user_hooks.register(reg, deps)
    memory.register(reg, deps)
    pages.register(reg, deps)
    ask.register(reg, deps)
    return reg


__all__ = ["CapabilityDeps", "build_agent_registry"]
