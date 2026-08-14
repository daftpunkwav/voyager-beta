"""事件契约:信封结构与事件类型词汇表。

每条事件必带 id / type / actor / payload / ts / trace_id(§7.2)。
事件类型词汇表是初始集,不封闭:新增事件类型只需在各服务注册并使用,
无需改动本包;常用类型沉淀到这里供三方共享。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActorKind(str, Enum):
    """行为者类别。本地单用户阶段 user 恒为 id="local",结构为多用户预留。

    system 为三类之外的基础设施身份:健康探测、进程监督等平台设施自身的行动,
    与用户/agent 的行为在审计与事件中区分。
    """

    USER = "user"
    AGENT = "agent"
    EXTERNAL = "external"
    SYSTEM = "system"


@dataclass(frozen=True)
class ActorRef:
    """事件与调用链上携带的行为者引用(纯数据)。"""

    kind: ActorKind
    id: str
    scopes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "id": self.id, "scopes": list(self.scopes)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActorRef:
        return cls(
            kind=ActorKind(data["kind"]),
            id=str(data["id"]),
            scopes=tuple(data.get("scopes") or ()),
        )


#: 本地单用户阶段的恒定 user actor(§7.4)
LOCAL_USER = ActorRef(kind=ActorKind.USER, id="local")


def new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Event:
    """事件信封。ts 为 epoch 秒(float);payload 必须可 JSON 序列化。"""

    type: str
    actor: ActorRef
    payload: dict[str, Any]
    trace_id: str = field(default_factory=new_trace_id)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "actor": self.actor.to_dict(),
            "payload": self.payload,
            "ts": self.ts,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            actor=ActorRef.from_dict(data["actor"]),
            payload=dict(data.get("payload") or {}),
            ts=float(data["ts"]),
            trace_id=str(data.get("trace_id") or ""),
        )


class DomainEvent:
    """领域事件词汇表(初始集,不封闭,§7.2)。"""

    USER_MESSAGE = "user.message"
    USER_ONLINE = "user.online"
    USER_ACTIVITY = "user.activity"
    TASK_ENQUEUED = "task.enqueued"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    AGENT_MESSAGE = "agent.message"
    AGENT_NAVIGATE = "agent.navigate"
    SETTINGS_CHANGED = "settings.changed"
    SERVICE_HEALTH_CHANGED = "service.health.changed"


class RuntimeEvent:
    """runtime 级事件(agent 内部,§7.2 / §9.1)。"""

    RUN_STARTED = "RunStarted"
    LLM_STARTED = "LLMStarted"
    LLM_STREAMING = "LLMStreaming"
    LLM_COMPLETED = "LLMCompleted"
    TOOL_STARTED = "ToolStarted"
    TOOL_COMPLETED = "ToolCompleted"
    TOOL_FAILED = "ToolFailed"
    AGENT_PAUSED = "AgentPaused"
    AGENT_RESUMED = "AgentResumed"
    AGENT_COMPLETED = "AgentCompleted"
    RUN_FAILED = "RunFailed"
