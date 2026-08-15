"""graph 能力注册表(§8.4,初始集;完整工具集在 docs/modules/graph.md 演进)。

- 队列类:enqueue_index / cancel_index / reorder_queue / list_index_jobs;
- 写入原语:set_node / set_relationship(AI 管线,upsert 语义,校验经 guide);
- 读取类:query_graph / get_subgraph / graph_stats / engine_info;
- 修订自旧 graph_service:读取统一走规范图存储,不再直达引擎。
"""

from __future__ import annotations

from dataclasses import dataclass

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, JobRef, ServiceError
from platform_eventbus import EventBus

from .engines.adapter import EngineAdapter
from .index_queue import IndexQueue
from .pipelines.ai import guide as ai_guide
from .store import GraphStore

_DOMAIN = "graph"
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    store: GraphStore
    queue: IndexQueue
    adapter: EngineAdapter
    bus: EventBus | None


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


# ---------- 队列类 ----------

@capability(registry, name="enqueue_index", description="源码索引入队(长任务;进度经 task.* 事件)",
            long_running=True, cost=5)
def enqueue_index(project: str, repo_path: str, priority: int = 100) -> JobRef:
    deps = _require_deps()
    jid = deps.queue.enqueue(project, repo_path, priority)
    return JobRef(job_id=jid)


@capability(registry, name="cancel_index", description="取消排队中的索引任务")
def cancel_index(job_id: str) -> dict:
    deps = _require_deps()
    if not deps.queue.cancel(job_id):
        raise ServiceError(_DOMAIN, ErrorSuffix.CONFLICT,
                           "仅排队中的任务可取消(运行中任务的协作式停止在演进中)")
    return {"cancelled": job_id}


@capability(registry, name="reorder_queue", description="调整索引队列优先级(数值小者优先)")
def reorder_queue(job_id: str, priority: int) -> dict:
    deps = _require_deps()
    if not deps.queue.reorder(job_id, priority):
        raise ServiceError(_DOMAIN, ErrorSuffix.CONFLICT, "任务不在排队中,无法调整")
    return {"job_id": job_id, "priority": priority}


@capability(registry, name="list_index_jobs", description="索引队列与历史任务")
def list_index_jobs(status: str = "") -> list[dict]:
    return _require_deps().queue.list(status)


# ---------- AI 管线写入原语 ----------

@capability(registry, name="set_node", description="AI 建图:写入/更新节点(upsert)", cost=2)
def set_node(project: str, label: str, name: str, qualified_name: str = "",
             attrs: dict | None = None, _actor: ActorRef = None) -> dict:
    ai_guide.validate_node(project, label, name)
    deps = _require_deps()
    actor_id = _actor.id if _actor else ""
    source = "ai" if (_actor and _actor.kind.value == "agent") else "manual"
    return deps.store.upsert_node(project, label, name, qualified_name, attrs,
                                  source=source, actor=actor_id)


@capability(registry, name="set_relationship",
            description="AI 建图:写入/更新关系;两端节点不存在时自动补占位节点", cost=2)
def set_relationship(project: str, src: str, dst: str, type: str,
                     attrs: dict | None = None, _actor: ActorRef = None) -> dict:
    ai_guide.validate_relation(project, src, dst, type)
    deps = _require_deps()
    actor_id = _actor.id if _actor else ""
    source = "ai" if (_actor and _actor.kind.value == "agent") else "manual"

    def _ensure(qn: str) -> str:
        for row in deps.store.query(project, keyword=qn, limit=5)["nodes"]:
            if row["qualified_name"] == qn:
                return row["id"]
        node = deps.store.upsert_node(project, "Term", qn, qn,
                                      {"placeholder": True}, source=source,
                                      actor=actor_id)
        return node["id"]

    return deps.store.upsert_edge(project, _ensure(src), _ensure(dst), type, attrs,
                                  source=source, actor=actor_id)


@capability(registry, name="graph_guide", description="AI 建图约定全文(agent 按需加载,§9.20)")
def graph_guide() -> dict:
    return {"guide": ai_guide.guide_text()}


# ---------- 读取类 ----------

@capability(registry, name="query_graph", description="查询项目图(可按标签/关键词过滤)")
def query_graph(project: str, label: str = "", keyword: str = "",
                limit: int = 200) -> dict:
    return _require_deps().store.query(
        project, label=label or None, keyword=keyword, limit=limit)


@capability(registry, name="get_subgraph", description="从节点出发的邻居展开(深度可调)")
def get_subgraph(project: str, node_id: str, depth: int = 1) -> dict:
    return _require_deps().store.subgraph(project, node_id, depth)


@capability(registry, name="graph_stats", description="图统计:按标签/类型的节点边计数")
def graph_stats(project: str) -> dict:
    return _require_deps().store.stats(project)


@capability(registry, name="list_projects", description="已有图数据的项目清单")
def list_projects() -> list[str]:
    return _require_deps().store.list_projects()


@capability(registry, name="engine_info", description="当前引擎与降级状态(引擎徽章数据源)")
async def engine_info() -> dict:
    deps = _require_deps()
    engine, name = await deps.adapter.resolve()
    return {"engine": name, "healthy": await engine.health()}


@capability(registry, name="drop_project_graph", description="删除项目的全部节点与边",
            reversible=False)
def drop_project_graph(project: str) -> dict:
    return _require_deps().store.drop_project(project)
