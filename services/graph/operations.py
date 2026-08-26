"""图读取/维护的大粒度操作(H4 拆分):邻居展开、路径、合并与导出。

函数形态接收 GraphStore 实例,复用其连接、列常量与行助手(同包内私有
约定);store 上的同名方法为一行委托,§8.1 对外 API 不变。读原语
(query/subgraph/upsert/drop)仍在 store.py。
"""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from .columns import _EDGE_COLS, _NODE_COLS, _edge_row, _node_row


def neighbors(store, project: str, node_id: str, *, depth: int = 1,
              edge_filter: str = "") -> dict[str, Any]:
    """邻居展开:从 node_id 出发按深度扩边,可选边类型过滤。"""
    seen_nodes: dict[str, dict] = {}
    seen_edges: dict[str, dict] = {}
    frontier = {node_id}
    all_edges = [
        _edge_row(r)
        for r in store._conn.execute(
            f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
        )
        if not edge_filter or r[4] == edge_filter
    ]
    for _ in range(max(depth, 0)):
        if not frontier:
            break
        qmarks = ",".join("?" for _ in frontier)
        for r in store._conn.execute(
            f"SELECT {','.join(_NODE_COLS)} FROM nodes"
            f" WHERE project = ? AND id IN ({qmarks})", (project, *frontier),
        ):
            n = _node_row(r)
            seen_nodes[n["id"]] = n
        nxt = set()
        for e in all_edges:
            if e["src"] in frontier or e["dst"] in frontier:
                seen_edges[e["id"]] = e
                for end in (e["src"], e["dst"]):
                    if end not in seen_nodes:
                        nxt.add(end)
        frontier = nxt
    # 最后一轮也要把 frontier 中的节点加载进来
    if frontier:
        qmarks = ",".join("?" for _ in frontier)
        for r in store._conn.execute(
            f"SELECT {','.join(_NODE_COLS)} FROM nodes"
            f" WHERE project = ? AND id IN ({qmarks})", (project, *frontier),
        ):
            n = _node_row(r)
            seen_nodes[n["id"]] = n
    return {"project": project, "nodes": list(seen_nodes.values()),
            "edges": list(seen_edges.values())}


def find_path(store, project: str, a: str, b: str, *, max_hops: int = 4,
              edge_filter: str = "") -> dict[str, Any]:
    """BFS 找 a→b 的短路径(max_hops 限深)。"""
    edges = [
        _edge_row(r)
        for r in store._conn.execute(
            f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
        )
        if not edge_filter or r[4] == edge_filter
    ]
    adj: dict[str, list[tuple[str, str, str]]] = {}
    for e in edges:
        adj.setdefault(e["src"], []).append((e["dst"], e["type"], e["id"]))
        adj.setdefault(e["dst"], []).append((e["src"], e["type"], e["id"]))

    if a == b:
        node = store._node_by_id(project, a)
        return {"project": project, "path": [node] if node else [],
                "edges": [], "found": node is not None}

    queue: deque[tuple[str, list[str], list[str]]] = deque([(a, [a], [])])
    visited: set[str] = {a}
    while queue:
        cur, path, path_edges = queue.popleft()
        if len(path) > max_hops + 1:
            continue
        for nxt, type_, eid in adj.get(cur, []):
            if nxt in visited:
                continue
            new_path = path + [nxt]
            new_edges = path_edges + [eid]
            if nxt == b:
                nodes = [store._node_by_id(project, nid) for nid in new_path]
                edge_rows = [store._edge_by_id(project, eid) for eid in new_edges]
                return {"project": project, "path": [n for n in nodes if n],
                        "edges": [e for e in edge_rows if e], "found": True}
            visited.add(nxt)
            queue.append((nxt, new_path, new_edges))
    return {"project": project, "path": [], "edges": [], "found": False}


def merge_nodes(store, project: str, keep: str, drop: str) -> dict[str, Any]:
    """合并两个节点:保留 keep,把指向 drop 的边迁到 keep,然后删除 drop。"""
    with store._lock:
        store._conn.execute(
            "UPDATE OR IGNORE edges SET src=?, updated_ts=?"
            " WHERE project=? AND src=? AND src!=?",
            (keep, time.time(), project, drop, keep),
        )
        store._conn.execute(
            "UPDATE OR IGNORE edges SET dst=?, updated_ts=?"
            " WHERE project=? AND dst=? AND dst!=?",
            (keep, time.time(), project, drop, keep),
        )
        store._conn.execute(
            "DELETE FROM edges WHERE project=? AND (src=? OR dst=?)",
            (project, drop, drop),
        )
        store._conn.execute(
            "DELETE FROM nodes WHERE project=? AND id=?", (project, drop),
        )
        store._conn.commit()
    return {"project": project, "kept": keep, "dropped": drop,
            "node": store._node_by_id(project, keep)}


def export_subgraph(store, project: str, node_id: str, *, depth: int = 2,
                    fmt: str = "json") -> dict[str, Any]:
    """导出子图为 JSON/CYPHER。

    Cypher 侧:标识符经反引号转义(内部反引号加倍),字符串值用
    json.dumps——防 AI 开放词表中的 label/type 逃逸语句结构。
    """
    sub = store.subgraph(project, node_id, depth)
    if fmt == "cypher":
        lines = []
        for n in sub["nodes"]:
            props = ", ".join(
                f"{k}: {json.dumps(v, ensure_ascii=False)}"
                for k, v in (("id", n["id"]), ("name", n["name"]),
                             ("qualified_name", n["qualified_name"]))
            )
            lines.append(f"CREATE (n:{_cypher_ident(n['label'])} {{{props}}})")
        for e in sub["edges"]:
            lines.append(
                f"MATCH (a {{id: {json.dumps(e['src'])}}}),"
                f" (b {{id: {json.dumps(e['dst'])}}})"
                f" CREATE (a)-[:{_cypher_ident(e['type'])}]->(b)"
            )
        sub["cypher"] = "\n".join(lines)
    return {"project": project, "format": fmt, **sub}


def _cypher_ident(name: str) -> str:
    """Cypher 标识符转义:反引号包裹,内部反引号加倍(官方规则)。"""
    return "`" + name.replace("`", "``") + "`"
