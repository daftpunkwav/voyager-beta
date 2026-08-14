"""capability 输入输出的共享 DTO(纯数据)。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class JobRef:
    """长任务约定(§7.3):handler 只入队并立即返回本引用,进度走事件流。"""

    job_id: str
    status: JobStatus = JobStatus.QUEUED

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "status": self.status.value}


class HealthStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HealthReport:
    """单个服务的健康快照(§7.10)。"""

    service: str
    status: HealthStatus
    detail: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "status": self.status.value,
            "detail": self.detail,
            "ts": self.ts,
        }
