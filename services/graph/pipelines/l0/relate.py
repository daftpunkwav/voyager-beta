"""L0 管线·跨资源关联(§8.4):资源库元数据 → universe 命名空间的关联图。

分层约定:L0 = 跨资源关联层(本模块);L1 = 单资源深度分析
(code 仓库走 engines(C/Python),其余类型由 AI 管线 agent 建图)。

资源清单经 wiring 注入的 resource_provider 回调取得(形状与 sources
`list_sources` 摘要对齐)——graph 不 import sources,依赖倒置到装配根。
当前关联规则是确定性的标签重合兜底(source="meta");AI 管线的语义
关联是叠加项(set_node/set_relationship,source="ai"),重建时保留。
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

from ...store import GraphStore

#: L0 关联图的项目命名空间
L0_PROJECT = "universe"

#: 参与关联的资源种类(与 sources list_sources 的 kind 对齐)
L0_KINDS = ("repo", "doc", "web")

#: 未就绪/失败的资源不参与关联
_EXCLUDED_STATUS = {"failed", "importing", "parsing"}

#: 单次分析的资源上限(两两比对 O(n²) 的保护)
MAX_RESOURCES = 1000

#: 资源清单提供者:(kinds) -> [{id, kind, title, tags, category, status, ...}]
ResourceProvider = Callable[[list[str]], list[dict[str, Any]]]


def run_l0(store: GraphStore, resource_provider: ResourceProvider | None, *,
           kinds: list[str]) -> dict[str, Any]:
    """重建 universe 空间的 meta 关联图;返回统计。

    幂等:先清理旧 meta 边与已消失的资源节点(保留 AI 产出),再按当前
    资源快照全量重写节点与标签重合边。
    """
    if resource_provider is None:
        raise RuntimeError(
            "L0 关联分析需要资源目录:请在聚合形态运行"
            "(deploy 注入 resource_provider),或先在资源库导入资源")
    unknown = [k for k in kinds if k not in L0_KINDS]
    if unknown:
        raise ValueError(f"未知的资源种类: {unknown}(可选: {list(L0_KINDS)})")
    if not kinds:
        raise ValueError("kinds 不能为空:至少选择一种资源参与关联分析")

    raw = resource_provider(list(kinds))
    resources = [r for r in raw if str(r.get("status", "ready"))
                 not in _EXCLUDED_STATUS]
    truncated = len(resources) > MAX_RESOURCES
    if truncated:
        # 截断保证确定性:按 (kind, id) 排序后取前 MAX_RESOURCES
        resources.sort(key=lambda r: (str(r.get("kind")), str(r.get("id"))))
        resources = resources[:MAX_RESOURCES]

    purged = store.purge_meta(L0_PROJECT, keep_qn={
        _qn(r) for r in resources})

    nodes = 0
    node_ids: dict[str, str] = {}
    for r in resources:
        row = store.upsert_node(
            L0_PROJECT, "Resource", str(r.get("title") or r.get("id")),
            _qn(r),
            {"kind": str(r.get("kind")),
             "tags": list(r.get("tags") or []),
             "category": str(r.get("category") or ""),
             "status": str(r.get("status", "ready")),
             "subtitle": str(r.get("subtitle") or "")},
            source="meta", actor="pipeline.l0")
        node_ids[_qn(r)] = row["id"]
        nodes += 1

    edges = 0
    by_tags = [(r, {t for t in (r.get("tags") or []) if t}) for r in resources]
    for (ra, ta), (rb, tb) in itertools.combinations(by_tags, 2):
        shared = sorted(ta & tb)
        if not shared:
            continue
        store.upsert_edge(
            L0_PROJECT, node_ids[_qn(ra)], node_ids[_qn(rb)], "RELATED",
            {"shared_tags": shared},
            source="meta", actor="pipeline.l0")
        edges += 1

    return {"project": L0_PROJECT, "kinds": list(kinds),
            "resources": len(resources), "nodes": nodes,
            "related_edges": edges,
            "purged_nodes": purged["nodes"], "purged_edges": purged["edges"],
            "truncated": truncated}


def l0_view(store: GraphStore, *, kinds: list[str] | None = None,
            limit: int = 500) -> dict[str, Any]:
    """读取 L0 视图:universe 节点/边(可按资源种类过滤)+ 并入跨仓关联边。

    CROSS_REPO 边原生存于 cross-repo 空间(端点是 L1 索引的 Project 节点,
    qualified_name=项目 id);此处把端点解析映射到 universe 的 repo 资源
    节点(repo:{id}),映射不到的边丢弃——视图内不出现悬空端点。
    """
    want = {k for k in (kinds or []) if k}
    graph = store.query(L0_PROJECT, limit=limit)
    if want:
        nodes = [n for n in graph["nodes"]
                 if str(n["attrs"].get("kind")) in want]
    else:
        nodes = graph["nodes"]
    ids = {n["id"] for n in nodes}
    edges = [e for e in graph["edges"] if e["src"] in ids and e["dst"] in ids]

    # cross-repo Project 节点:qualified_name = 项目 id(L1 enqueue 的 project);
    # universe 的 repo 资源节点 qn = "repo:{id}",两者同源可直接拼接映射
    proj_qn = {n["id"]: n["qualified_name"]
               for n in store.query("cross-repo", label="Project",
                                    limit=10000)["nodes"]}
    universe_repo = {n["qualified_name"]: n["id"] for n in nodes
                     if str(n["attrs"].get("kind")) == "repo"}
    cross: list[dict[str, Any]] = []
    for e in store.cross_edges():
        a = universe_repo.get(f"repo:{proj_qn.get(e['src'], '')}")
        b = universe_repo.get(f"repo:{proj_qn.get(e['dst'], '')}")
        if a in ids and b in ids:
            cross.append({**e, "src": a, "dst": b})
    return {"nodes": nodes, "edges": edges, "cross_edges": cross}


def _qn(r: dict[str, Any]) -> str:
    return f"{r.get('kind')}:{r.get('id')}"
