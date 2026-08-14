"""能力注册表(单一事实来源,§8.1)。

模式:模块级 registry + init_deps() 注入运行依赖(store/bus/queue)。
handler 只写业务;鉴权/限流/审计由框架入口强制(§7.3)。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from platform_capability import Registry, capability
from platform_contracts import JobRef
from platform_eventbus import EventBus

from .store import JobStore

registry = Registry("template")


@dataclass
class Deps:
    """服务运行时依赖,由入口(rest.py / mcp_server.py)注入。"""

    store: JobStore
    bus: EventBus | None
    queue: asyncio.Queue  # 长任务队列:job_id


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


@dataclass
class EchoIn:
    text: str
    shout: bool = False


@capability(registry, name="echo", description="回显文本;shout=true 时转大写", input_model=EchoIn)
def echo(data: EchoIn) -> dict:
    return {"echo": data.text.upper() if data.shout else data.text}


@capability(registry, name="get_info", description="服务自检:名称/协议版本/待处理任务数")
def get_info() -> dict:
    deps = _require_deps()
    return {
        "service": "template",
        "protocol": "0.1.0",
        "pending_jobs": deps.queue.qsize(),
    }


@capability(
    registry,
    name="submit_job",
    description="提交一个示例长任务;立即返回 job_id,进度经事件流 task.progress/completed",
    long_running=True,
)
def submit_job() -> JobRef:
    """长任务约定(§7.3):只入队,不阻塞;worker.py 负责执行与进度事件。"""
    deps = _require_deps()
    job_id = uuid.uuid4().hex[:12]
    deps.store.enqueue(job_id)
    deps.queue.put_nowait(job_id)
    return JobRef(job_id=job_id)
