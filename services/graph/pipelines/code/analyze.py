"""程序化管线·源码分析(§8.4):引擎解析仓库 → 同步进规范图存储。

适配层屏蔽 C/Python 差异;引擎产出经 export 落入 store(source="code",
actor=引擎名)。仓库关联度分析在 relate.py。
"""

from __future__ import annotations

from typing import Any

from engines.adapter import EngineAdapter
from store import GraphStore


async def analyze_repo(
    adapter: EngineAdapter,
    store: GraphStore,
    *,
    project: str,
    repo_path: str,
    mode: str = "moderate",
) -> dict[str, Any]:
    """执行源码索引:引擎解析 → 导出节点/边到规范存储 → 回统计。"""
    engine, engine_name = await adapter.resolve()
    result = await engine.index_repository(repo_path, name=project, mode=mode)
    exported = await _export_to_canonical(engine, engine_name, store, project)
    return {"project": project, "engine": engine_name,
            "engine_result": result, **exported}


async def _export_to_canonical(engine: Any, engine_name: str,
                               store: GraphStore, project: str) -> dict[str, int]:
    """把引擎内图导出到规范存储(upsert 幂等;重复索引不产生重复节点)。"""
    graph = await engine.call("search_graph", {"project": project, "limit": 100000})
    nodes = graph.get("nodes") or graph.get("results") or []
    edges = graph.get("edges") or []
    for n in nodes:
        store.upsert_node(
            project,
            str(n.get("label") or "Unknown"),
            str(n.get("name") or ""),
            str(n.get("qualified_name") or n.get("qualifiedName") or n.get("name") or ""),
            n.get("attrs") or {},
            source="code", actor=f"engine.{engine_name}",
        )
    for e in edges:
        store.upsert_edge(
            project,
            str(e.get("src") or e.get("from") or ""),
            str(e.get("dst") or e.get("to") or ""),
            str(e.get("type") or "RELATED"),
            e.get("attrs") or {},
            source="code", actor=f"engine.{engine_name}",
        )
    return {"exported_nodes": len(nodes), "exported_edges": len(edges)}
