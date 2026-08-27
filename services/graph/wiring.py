"""graph 装配:独立运行(rest.py)与聚合运行(deploy/)的唯一接线来源。

scheduler 默认由本服务自建;测试或装配根需要替换调度策略时可注入。
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import Deps, init_deps, registry
from .engines.adapter import EngineAdapter
from .index_queue import IndexQueue
from .pipelines.code.analyze import analyze_repo
from .pipelines.l0 import relate as l0_relate
from .scheduler import IndexScheduler
from .settings import DEFS
from .store import GraphStore


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    c_url: str = "http://127.0.0.1:8123",
    engine_mode: str = "auto",
    scheduler: IndexScheduler | None = None,
    settings_store: SettingsStore | None = None,
    resource_provider: l0_relate.ResourceProvider | None = None,
) -> Wiring:
    data_dir = Path(data_dir)
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    store = GraphStore(data_dir / "graph.db")
    queue = IndexQueue(data_dir / "index.db")
    adapter = EngineAdapter(c_base_url=c_url,
                            python_data_root=data_dir / "engine-python",
                            bus=bus, mode=engine_mode)
    init_deps(Deps(store=store, queue=queue, adapter=adapter, bus=bus,
                   resource_provider=resource_provider))

    async def _run_job(job: dict) -> None:
        # 任务分派按 level(§8.4 分层):l1=单资源深度(code 引擎);
        # l0=跨资源关联(元数据兜底;AI 语义关联由 agent 经写入原语叠加)
        if job.get("level") == "l0":
            l0_relate.run_l0(store, resource_provider, kinds=job.get("kinds") or [])
            return
        await analyze_repo(adapter, store, project=job["project"],
                           repo_path=job["repo_path"])

    sched = scheduler or IndexScheduler(queue, _run_job, bus)

    def probe() -> dict:
        return {"status": "up", "engine_mode": engine_mode}

    def close() -> None:
        store.close()
        queue.close()

    return Wiring(
        registry=registry,
        probe=probe,
        start=sched.start,
        stop=sched.stop,
        close=close,
    )
