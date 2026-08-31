"""agent 能力依赖袋子。

保持为一个 dataclass,每次 build_agent_registry 时由 main.py 注入。
禁止拆字段,禁止模块级全局 _deps。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.context.pages import PageContextRegistry
from agent.memory import Memory
from agent.skills.loader import SkillLoader
from agent.subagent.registry import SubagentRegistry
from agent.subagent.spawn import Spawner
from agent.tools.ask_user import AskUser


@dataclass
class CapabilityDeps:
    settings: Any  # SettingsStore
    memory: Memory
    skills: SkillLoader
    spawner: Spawner
    subagents: SubagentRegistry
    pages: PageContextRegistry
    asker: AskUser
    toolbelt: Any  # Toolbelt(list_tools 数据源,§9.4)
    mcp: Any  # McpClientPool(外接 MCP,phase-11b;配置写经 actor 落审计)
