"""程序化管线·源码分析(§8.4):引擎解析仓库 -> 同步进规范图存储。

适配层屏蔽 C/Python 差异;引擎产出经 export 落入 store(source="code",
actor=引擎名)。索引完成后自动跑仓库关联(relate,§8.4);边导出时把
引擎节点 id 映射为规范存储 id(两侧 id 空间不同)。
"""

from __future__ import annotations

from typing import Any

from ...engines.adapter import EngineAdapter
from ...store import GraphStore
from .relate import relate_repos


async def analyze_repo(
    adapter: EngineAdapter,
    store: GraphStore,
    *,
    project: str,
    repo_path: str,
    mode: str = "moderate",
) -> dict[str, Any]:
    """执行源码索引:引擎解析 -> 导出节点/边到规范存储 -> 跨仓关联 -> 回统计。"""
    engine, engine_name = await adapter.resolve()
    result = await engine.index_repository(repo_path, name=project, mode=mode)
    exported = await _export_to_canonical(engine, engine_name, store, project)
    related = relate_repos(store, _indexed_projects(store, project))
    return {"project": project, "engine": engine_name,
            "engine_result": result, **exported, "relate": related}


def _indexed_projects(store: GraphStore, current: str) -> list[str]:
    """有关联意义的项目集:当前项目 + 图中已有代码节点(来源 code)的其他项目。"""
    projects = {current}
    rows = store.list_code_projects()
    projects.update(rows)
    projects.discard("cross-repo")
    return sorted(projects)


async def _export_to_canonical(engine: Any, engine_name: str,
                               store: GraphStore, project: str) -> dict[str, int]:
    """把引擎内图导出到规范存储(upsert 幂等;重复索引不产生重复节点)。

    引擎节点 id 与规范存储 id 是两个空间:先 upsert 节点并记录
    引擎 id -> 规范 id 映射,边按映射改写端点,悬空端点丢弃。
    """
    graph = await engine.call("export_graph", {"project": project})
    nodes = graph.get("nodes") or graph.get("results") or []
    edges = graph.get("edges") or []
    id_map: dict[str, str] = {}
    for n in nodes:
        qn = str(n.get("qualified_name") or n.get("qualifiedName")
                 or n.get("name") or "")
        row = store.upsert_node(
            project,
            str(n.get("label") or "Unknown"),
            str(n.get("name") or qn),
            qn,
            n.get("attrs") or {},
            source="code", actor=f"engine.{engine_name}",
        )
        engine_id = str(n.get("id") or "")
        if engine_id:
            id_map[engine_id] = row["id"]
    mapped = 0
    for e in edges:
        src = id_map.get(str(e.get("src") or e.get("from") or ""))
        dst = id_map.get(str(e.get("dst") or e.get("to") or ""))
        if not src or not dst:
            continue
        store.upsert_edge(project, src, dst,
                          str(e.get("type") or "RELATED"), e.get("attrs") or {},
                          source="code", actor=f"engine.{engine_name}")
        mapped += 1
    return {"exported_nodes": len(nodes), "exported_edges": mapped}
