"""运行状态与断点(§9.1):run/step 状态机 + checkpoint 落盘可恢复。"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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
        path = self._root / f"{state.run_id}.json"
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, run_id: str) -> RunState:
        path = self._root / f"{run_id}.json"
        return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_alive(self) -> list[RunState]:
        out = []
        for path in sorted(self._root.glob("*.json")):
            state = RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if state.status.alive:
                out.append(state)
        return out

    def delete(self, run_id: str) -> None:
        (self._root / f"{run_id}.json").unlink(missing_ok=True)
