"""graph 能力注册表(§8.4,初始集;完整工具集在 docs/modules/graph.md 演进)。

- 队列类:enqueue_index / cancel_index / reorder_queue / list_index_jobs;
- 写入原语:set_node / set_relationship(AI 管线,upsert 语义,校验经 guide);
- 读取类:query_graph / get_subgraph / graph_stats / engine_info;
- 修订自旧 graph_service:读取统一走规范图存储,不再直达引擎。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, JobRef, ServiceError
from platform_eventbus import EventBus

from .engines.adapter import EngineAdapter
from .index_queue import IndexQueue
from .pipelines.ai import guide as ai_guide
from .pipelines.l0 import relate as l0_relate
from .store import GraphStore

_DOMAIN = "graph"
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    store: GraphStore
    queue: IndexQueue
    adapter: EngineAdapter
    bus: EventBus | None
    #: L0 资源清单回调(kinds -> 资源摘要);聚合形态由装配根注入
    resource_provider: l0_relate.ResourceProvider | None = None
    #: 索引路径 jail;wire() 注入 workspace,未注入时入队不校验(单测队列用)
    workspace: Path | None = None


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps 未注入:服务入口需先调用 init_deps()")
    return _deps


def _ensure_node_id(store: GraphStore, project: str, qn: str, *,
                    source: str, actor: str) -> str:
    """按 qualified_name 找节点 id;不存在则补占位 Term 节点(set_relationship 共用)。"""
    for row in store.query(project, keyword=qn, limit=5)["nodes"]:
        if row["qualified_name"] == qn:
            return row["id"]
    node = store.upsert_node(project, "Term", qn, qn, {"placeholder": True},
                             source=source, actor=actor)
    return node["id"]


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


# ---------- 队列类 ----------

@capability(registry, name="enqueue_index",
            description="L1 源码索引入队(code 仓库深度分析;长任务,进度经 task.* 事件)",
            long_running=True, cost=5)
def enqueue_index(project: str, repo_path: str, priority: int = 100) -> JobRef:
    deps = _require_deps()
    if deps.workspace is not None and not _within(Path(repo_path), deps.workspace):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.FORBIDDEN,
            "索引路径须位于 workspace/ 内",
            hint="先把仓库放到 workspace/repo 再入队,禁止扫 jail 外目录",
        )
    jid = deps.queue.enqueue(project, repo_path, priority, level="l1")
    return JobRef(job_id=jid)


@capability(registry, name="enqueue_l0",
            description="L0 跨资源关联分析入队(kinds 选资源种类子集;"
                        "标签重合兜底,AI 语义关联叠加)",
            long_running=True, cost=3)
def enqueue_l0(kinds: list[str], priority: int = 100) -> JobRef:
    deps = _require_deps()
    unknown = [k for k in kinds if k not in l0_relate.L0_KINDS]
    if unknown:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"未知的资源种类: {unknown}(可选: {list(l0_relate.L0_KINDS)})")
    if not kinds:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "kinds 不能为空:至少选择一种资源参与关联分析")
    jid = deps.queue.enqueue(l0_relate.L0_PROJECT, "", priority,
                             level="l0", kinds=sorted(set(kinds)))
    return JobRef(job_id=jid)


@capability(registry, name="l0_view",
            description="L0 关联图视图(universe 空间节点/边,可按资源种类过滤;"
                        "含跨仓关联边)")
def l0_view(kinds: list[str] | None = None, limit: int = 500) -> dict:
    return l0_relate.l0_view(_require_deps().store, kinds=kinds,
                             limit=min(limit, 2000))


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

    return deps.store.upsert_edge(
        project,
        _ensure_node_id(deps.store, project, src, source=source, actor=actor_id),
        _ensure_node_id(deps.store, project, dst, source=source, actor=actor_id),
        type, attrs, source=source, actor=actor_id)


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


# ---------- 规划工具(按 docs/modules/graph.md 演进) ----------

@capability(registry, name="expand_neighbors",
            description="邻居展开:从节点出发按深度扩边,可选边类型过滤")
def expand_neighbors(project: str, node_id: str, depth: int = 1,
                     edge_filter: str = "") -> dict:
    return _require_deps().store.neighbors(
        project, node_id, depth=depth, edge_filter=edge_filter)


@capability(registry, name="find_path",
            description="在图中找 a→b 的短路径(双向 BFS)")
def find_path(project: str, a: str, b: str, max_hops: int = 4,
              edge_filter: str = "") -> dict:
    return _require_deps().store.find_path(
        project, a, b, max_hops=max_hops, edge_filter=edge_filter)


@capability(registry, name="set_nodes",
            description="批量写入/更新节点(减少 AI 管线往返)")
def set_nodes(project: str, nodes: list[dict]) -> dict:
    ai_guide.validate_nodes_batch(project, nodes)
    deps = _require_deps()
    out = []
    for n in nodes:
        out.append(deps.store.upsert_node(
            project, n["label"], n["name"], n.get("qualified_name", ""),
            n.get("attrs"), source="ai", actor="agent.batch"))
    return {"project": project, "count": len(out), "nodes": out}


@capability(registry, name="set_relationships",
            description="批量写入/更新关系(自动补占位节点)")
def set_relationships(project: str, relations: list[dict]) -> dict:
    ai_guide.validate_relations_batch(project, relations)
    deps = _require_deps()
    out = []
    for r in relations:
        src = r["src"]
        dst = r["dst"]
        out.append(deps.store.upsert_edge(
            project,
            _ensure_node_id(deps.store, project, src, source="ai", actor="agent.batch"),
            _ensure_node_id(deps.store, project, dst, source="ai", actor="agent.batch"),
            r["type"], r.get("attrs"), source="ai", actor="agent.batch"))
    return {"project": project, "count": len(out), "edges": out}


@capability(registry, name="merge_nodes",
            description="合并两个节点:保留 keep,把 drop 的边迁到 keep")
def merge_nodes(project: str, keep: str, drop: str) -> dict:
    return _require_deps().store.merge_nodes(project, keep, drop)


@capability(registry, name="export_subgraph",
            description="导出子图(JSON/CYPHER)")
def export_subgraph(project: str, node_id: str, depth: int = 2,
                    format: str = "json") -> dict:
    return _require_deps().store.export_subgraph(
        project, node_id, depth=depth, fmt=format)
