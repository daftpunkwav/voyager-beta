"""Agent 共享类型 —— 消息、工作流枚举、引擎配置"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias, TypedDict


class Message(TypedDict, total=False):
    """单条 LLM 消息（role/content/tool 字段均可选，随角色而定）。"""

    role: str
    content: str | None
    tool_calls: list[dict[str, Any]]
    tool_call_id: str


Messages: TypeAlias = list[Message]


class Workflow(str, Enum):
    """Agent 工作流枚举（str 子类，兼容既有字符串配置与比较）。"""

    COT = "cot"
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    REFLEXION = "reflexion"
    TOT = "tot"
    DIRECT = "direct"


@dataclass(frozen=True)
class AgentEngineConfig:
    """引擎/编排阈值集中配置（原散落魔数），注入 ReActEngine / HubService，测试可覆盖。"""

    expert_summary_chars: int = 6000
    expert_history_window: int = 6
    max_hub_dispatch_rounds: int = 2
    max_iterations: int = 8
    tool_result_truncate: int = 12000
    tool_result_sse_limit: int = 4000
    preview_limit: int = 200
    closing_min_tokens: int = 2048
    plan_cap_default: int = 420
    plan_cap_tot: int = 900
    subagent_thinking_limit: int = 24000
    subagent_output_limit: int = 100_000
