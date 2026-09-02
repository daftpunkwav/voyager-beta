"""运行状态与断点(§9.1):run/step 状态机 + checkpoint 落盘可恢复。"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# run_id 直接拼进文件路径,必须是纯安全字符(防 ../../ 穿越到 checkpoints 之外)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(f"非法 run_id: {run_id!r}(仅允许字母/数字/下划线/连字符)")
    return run_id


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"  # 对话型 subagent 等用户下一句话
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def alive(self) -> bool:
        return self in (RunStatus.RUNNING, RunStatus.WAITING_INPUT, RunStatus.PAUSED)


@dataclass
class Step:
    n: int
    kind: str  # "llm" | "tool"
    name: str
    summary: str
    ts: float = field(default_factory=time.time)


@dataclass
class ResumeSnapshot:
    """恢复快照(phase-69,§9.17):重建 SubagentInstance 所需的最小全集。

    存进 RunState.resume(dict 形态);旧 checkpoint 无该键 = legacy,不可恢复。
    """

    instance_id: str
    instance_name: str
    persona: str
    goal: str
    constraints: str = ""
    done_when: str = ""
    mode: str = "react"  # Mode.value
    allowed_tools: list[str] | None = None
    max_rounds: int | None = None
    max_tool_calls: int | None = None
    conversational: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResumeSnapshot:
        return cls(**data)


@dataclass
class RunState:
    task: str
    subagent_id: str = ""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: RunStatus = RunStatus.PENDING
    steps: list[Step] = field(default_factory=list)
    rounds: int = 0
    tool_calls: int = 0
    result: str | None = None
    error: str = ""
    started_ts: float = field(default_factory=time.time)  # 实例耗时展示用
    resume: dict[str, Any] | None = None  # ResumeSnapshot.to_dict();None = legacy 不可恢复

    def add_step(self, kind: str, name: str, summary: str) -> Step:
        step = Step(n=len(self.steps) + 1, kind=kind, name=name, summary=summary)
        self.steps.append(step)
        return step

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        data = dict(data)
        data["status"] = RunStatus(data["status"])
        data["steps"] = [Step(**s) for s in data.get("steps", [])]
        data.setdefault("started_ts", 0.0)  # 旧 checkpoint 兼容
        return cls(**data)


class CheckpointStore:
    """runtime-data/checkpoints/<run_id>.json;崩溃恢复(§9.17)的事实来源。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, state: RunState) -> Path:
        path = self._root / f"{_safe_run_id(state.run_id)}.json"
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, run_id: str) -> RunState:
        path = self._root / f"{_safe_run_id(run_id)}.json"
        return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_alive(self) -> list[RunState]:
        """列出仍 alive 的 checkpoint;单份文件损坏则跳过,不挡其它 checkpoint、不挡启动。"""
        out = []
        for path in sorted(self._root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                state = RunState.from_dict(raw)
            except (
                json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError, TypeError, OSError
            ):
                continue
            if state.status.alive:
                out.append(state)
        return out

    def delete(self, run_id: str) -> None:
        (self._root / f"{_safe_run_id(run_id)}.json").unlink(missing_ok=True)


def reclaim_alive(store: CheckpointStore) -> list[RunState]:
    """启动 reclaim(§9.17,phase-12):进程重启时把磁盘上仍 alive 的 checkpoint
    全部标记 failed。本阶段不实现中途 resume,不据此重建实例;返回被标 failed
    的状态供启动日志/调用方知悉。"""
    out: list[RunState] = []
    for state in store.list_alive():
        state.status = RunStatus.FAILED
        state.error = "进程重启,任务未恢复"
        store.save(state)
        out.append(state)
    return out


def prepare_resumable_checkpoints(store: CheckpointStore) -> list[RunState]:
    """进程重启(§9.17,phase-69):有 resume 快照的 alive → PAUSED 待恢复;
    无快照的 legacy alive → 仍标 FAILED(与 reclaim_alive 旧行为一致)。
    返回被处理的状态供启动日志/调用方知悉;不据此重建实例(resume 走 capability)。"""
    out: list[RunState] = []
    for state in store.list_alive():
        if state.resume is not None:
            state.status = RunStatus.PAUSED
            state.error = "进程重启,可恢复"
        else:
            state.status = RunStatus.FAILED
            state.error = "进程重启,任务未恢复"
        store.save(state)
        out.append(state)
    return out
