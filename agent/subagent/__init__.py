"""Subagent 体系:派出、实例状态机、七种模式、用户自建注册。"""

from agent.subagent.instance import SubagentInstance, SubStatus, TaskBook
from agent.subagent.modes import Mode, ModeLimits, run_mode
from agent.subagent.registry import SubagentDef, SubagentRegistry
from agent.subagent.spawn import Spawner

__all__ = [
    "Mode",
    "ModeLimits",
    "Spawner",
    "SubStatus",
    "SubagentDef",
    "SubagentInstance",
    "SubagentRegistry",
    "TaskBook",
    "run_mode",
]
