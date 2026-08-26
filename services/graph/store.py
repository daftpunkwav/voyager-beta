"""graph 规范图存储(§8.4):同一份图,来源可区分(actor + pipeline)。

- 程序化管线的引擎产出经适配层同步进来(source="code");
- AI 管线 agent 经 set_node/set_relationship 直接写(source="ai");
- 用户手动建的节点 source="manual"。
自然键 (project, label, qualified_name) 保证 upsert 语义幂等。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id             TEXT PRIMARY KEY,
    project        TEXT NOT NULL,
    label          TEXT NOT NULL,
    name           TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    attrs          TEXT NOT NULL DEFAULT '{}',
    source         TEXT NOT NULL DEFAULT 'manual',
    actor          TEXT NOT NULL DEFAULT '',
    updated_ts     REAL NOT NULL,
    UNIQUE (project, label, qualified_name)
);
CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project, label);
CREATE TABLE IF NOT EXISTS edges (
    id         TEXT PRIMARY KEY,
    project    TEXT NOT NULL,
    src        TEXT NOT NULL,
    dst        TEXT NOT NULL,
    type       TEXT NOT NULL,
    attrs      TEXT NOT NULL DEFAULT '{}',
    source     TEXT NOT NULL DEFAULT 'manual',
    actor      TEXT NOT NULL DEFAULT '',
    updated_ts REAL NOT NULL,
    UNIQUE (project, src, dst, type)
);
CREATE INDEX IF NOT EXISTS idx_edges_project ON edges(project, type);
"""

_NODE_COLS = ("id", "project", "label", "name", "qualified_name",
              "attrs", "source", "actor", "updated_ts")
_EDGE_COLS = ("id", "project", "src", "dst", "type", "attrs",
              "source", "actor", "updated_ts")


def _node_id(project: str, label: str, qualified_name: str) -> str:
    return hashlib.sha1(f"{project}{label}{qualified_name}".encode()).hexdigest()[:16]


def _edge_id(project: str, src: str, dst: str, type_: str) -> str:
    return hashlib.sha1(f"{project}{src}{dst}{type_}".encode()).hexdigest()[:16]


class GraphStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def upsert_node(self, project: str, label: str, name: str,
                    qualified_name: str = "", attrs: dict | None = None,
                    *, source: str = "manual", actor: str = "") -> dict[str, Any]:
        qn = qualified_name or name
        nid = _node_id(project, label, qn)
        with self._lock:
            self._conn.execute(
                "INSERT INTO nodes (id, project, label, name, qualified_name, attrs,"
                " source, actor, updated_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(project, label, qualified_name) DO UPDATE SET"
                " name=excluded.name, attrs=excluded.attrs, source=excluded.source,"
                " actor=excluded.actor, updated_ts=excluded.updated_ts",
                (nid, project, label, name, qn,
                 json.dumps(attrs or {}, ensure_ascii=False), source, actor,
                 time.time()),
            )
            self._conn.commit()
        return self.get_node(project, label, qn)

    def get_node(self, project: str, label: str, qualified_name: str) -> dict | None:
        row = self._conn.execute(
            f"SELECT {','.join(_NODE_COLS)} FROM nodes"
            " WHERE project=? AND label=? AND qualified_name=?",
            (project, label, qualified_name),
        ).fetchone()
        return _row(_NODE_COLS, row) if row else None

    def upsert_edge(self, project: str, src: str, dst: str, type_: str,
                    attrs: dict | None = None,
                    *, source: str = "manual", actor: str = "") -> dict[str, Any]:
        eid = _edge_id(project, src, dst, type_)
        with self._lock:
            self._conn.execute(
                "INSERT INTO edges (id, project, src, dst, type, attrs, source, actor,"
                " updated_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(project, src, dst, type) DO UPDATE SET"
                " attrs=excluded.attrs, source=excluded.source, actor=excluded.actor,"
                " updated_ts=excluded.updated_ts",
                (eid, project, src, dst, type_,
                 json.dumps(attrs or {}, ensure_ascii=False), source, actor,
                 time.time()),
            )
            self._conn.commit()
        row = self._conn.execute(
            f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE id=?", (eid,)
        ).fetchone()
        return _row(_EDGE_COLS, row)

    def query(self, project: str, *, label: str | None = None,
              keyword: str = "", limit: int = 200) -> dict[str, Any]:
        conds, params = ["project = ?"], [project]
        if label:
            conds.append("label = ?")
            params.append(label)
        if keyword:
            conds.append("(name LIKE ? OR qualified_name LIKE ?)")
            params += [f"%{keyword}%", f"%{keyword}%"]
        nodes = [
            _row(_NODE_COLS, r)
            for r in self._conn.execute(
                f"SELECT {','.join(_NODE_COLS)} FROM nodes WHERE {' AND '.join(conds)}"
                " LIMIT ?", (*params, limit),
            )
        ]
        node_ids = {n["id"] for n in nodes}
        edges = []
        for r in self._conn.execute(
            f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
        ):
            e = _row(_EDGE_COLS, r)
            if e["src"] in node_ids and e["dst"] in node_ids:
                edges.append(e)
        return {"project": project, "nodes": nodes, "edges": edges}

    def subgraph(self, project: str, node_id: str, depth: int = 1) -> dict[str, Any]:
        """邻居展开:从 node_id 出发按深度扩边(两级加载的近端,§9.20)。"""
        seen_nodes: dict[str, dict] = {}
        seen_edges: dict[str, dict] = {}
        frontier = {node_id}
        all_edges = [
            _row(_EDGE_COLS, r)
            for r in self._conn.execute(
                f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
            )
        ]
        for _ in range(max(depth, 0) + 1):
            if not frontier:
                break
            qmarks = ",".join("?" for _ in frontier)
            for r in self._conn.execute(
                f"SELECT {','.join(_NODE_COLS)} FROM nodes"
                f" WHERE project = ? AND id IN ({qmarks})", (project, *frontier),
            ):
                n = _row(_NODE_COLS, r)
                seen_nodes[n["id"]] = n
            nxt = set()
            for e in all_edges:
                if e["src"] in frontier or e["dst"] in frontier:
                    seen_edges[e["id"]] = e
                    for end in (e["src"], e["dst"]):
                        if end not in seen_nodes:
                            nxt.add(end)
            frontier = nxt
        return {"project": project, "nodes": list(seen_nodes.values()),
                "edges": list(seen_edges.values())}

    def stats(self, project: str) -> dict[str, Any]:
        nodes = self._conn.execute(
            "SELECT label, COUNT(*) FROM nodes WHERE project = ? GROUP BY label",
            (project,),
        ).fetchall()
        edges = self._conn.execute(
            "SELECT type, COUNT(*) FROM edges WHERE project = ? GROUP BY type",
            (project,),
        ).fetchall()
        return {"project": project,
                "nodes_by_label": {r[0]: r[1] for r in nodes},
                "edges_by_type": {r[0]: r[1] for r in edges},
                "total_nodes": sum(r[1] for r in nodes),
                "total_edges": sum(r[1] for r in edges)}

    def list_projects(self) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT DISTINCT project FROM nodes ORDER BY project")]

    def list_code_projects(self) -> list[str]:
        """已有程序化管线产出的项目(跨仓关联的候选集)。"""
        return [r[0] for r in self._conn.execute(
            "SELECT DISTINCT project FROM nodes WHERE source = 'code'")]

    def neighbors(self, project: str, node_id: str, *, depth: int = 1,
                  edge_filter: str = "") -> dict[str, Any]:
        """邻居展开:从 node_id 出发按深度扩边,可选边类型过滤。"""
        seen_nodes: dict[str, dict] = {}
        seen_edges: dict[str, dict] = {}
        frontier = {node_id}
        all_edges = [
            _row(_EDGE_COLS, r)
            for r in self._conn.execute(
                f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
            )
            if not edge_filter or r[4] == edge_filter
        ]
        for _ in range(max(depth, 0)):
            if not frontier:
                break
            qmarks = ",".join("?" for _ in frontier)
            for r in self._conn.execute(
                f"SELECT {','.join(_NODE_COLS)} FROM nodes"
                f" WHERE project = ? AND id IN ({qmarks})", (project, *frontier),
            ):
                n = _row(_NODE_COLS, r)
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
            for r in self._conn.execute(
                f"SELECT {','.join(_NODE_COLS)} FROM nodes"
                f" WHERE project = ? AND id IN ({qmarks})", (project, *frontier),
            ):
                n = _row(_NODE_COLS, r)
                seen_nodes[n["id"]] = n
        return {"project": project, "nodes": list(seen_nodes.values()),
                "edges": list(seen_edges.values())}

    def find_path(self, project: str, a: str, b: str, *, max_hops: int = 4,
                  edge_filter: str = "") -> dict[str, Any]:
        """双向 BFS 找 a→b 的短路径。"""
        from collections import deque

        edges = [
            _row(_EDGE_COLS, r)
            for r in self._conn.execute(
                f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
            )
            if not edge_filter or r[4] == edge_filter
        ]
        adj: dict[str, list[tuple[str, str, str]]] = {}
        for e in edges:
            adj.setdefault(e["src"], []).append((e["dst"], e["type"], e["id"]))
            adj.setdefault(e["dst"], []).append((e["src"], e["type"], e["id"]))

        if a == b:
            node = self._node_by_id(project, a)
            return {"project": project, "path": [node] if node else [],
                    "edges": [], "found": node is not None}

        # BFS
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
                    nodes = [self._node_by_id(project, nid) for nid in new_path]
                    edge_rows = [self._edge_by_id(project, eid) for eid in new_edges]
                    return {"project": project, "path": [n for n in nodes if n],
                            "edges": [e for e in edge_rows if e], "found": True}
                visited.add(nxt)
                queue.append((nxt, new_path, new_edges))
        return {"project": project, "path": [], "edges": [], "found": False}

    def merge_nodes(self, project: str, keep: str, drop: str) -> dict[str, Any]:
        """合并两个节点:保留 keep,把指向 drop 的边迁到 keep,然后删除 drop。"""
        with self._lock:
            self._conn.execute(
                "UPDATE OR IGNORE edges SET src=?, updated_ts=?"
                " WHERE project=? AND src=? AND src!=?",
                (keep, time.time(), project, drop, keep),
            )
            self._conn.execute(
                "UPDATE OR IGNORE edges SET dst=?, updated_ts=?"
                " WHERE project=? AND dst=? AND dst!=?",
                (keep, time.time(), project, drop, keep),
            )
            self._conn.execute(
                "DELETE FROM edges WHERE project=? AND (src=? OR dst=?)",
                (project, drop, drop),
            )
            self._conn.execute(
                "DELETE FROM nodes WHERE project=? AND id=?",
                (project, drop),
            )
            self._conn.commit()
        return {"project": project, "kept": keep, "dropped": drop,
                "node": self._node_by_id(project, keep)}

    def export_subgraph(self, project: str, node_id: str, *, depth: int = 2,
                        fmt: str = "json") -> dict[str, Any]:
        """导出子图为 JSON/CYPHER。"""
        sub = self.subgraph(project, node_id, depth)
        if fmt == "cypher":
            lines = []
            for n in sub["nodes"]:
                name = n["name"].replace("'", "\\'")
                qn = n["qualified_name"].replace("'", "\\'")
                lines.append(
                    f"CREATE (n:{n['label']} {{id: '{n['id']}',"
                    f" name: '{name}',"
                    f" qualified_name: '{qn}'}})",
                )
            for e in sub["edges"]:
                lines.append(
                    f"MATCH (a {{id: '{e['src']}'}}), (b {{id: '{e['dst']}'}})"
                    f" CREATE (a)-[:{e['type']}]->(b)",
                )
            sub["cypher"] = "\n".join(lines)
        return {"project": project, "format": fmt, **sub}

    def _node_by_id(self, project: str, node_id: str) -> dict | None:
        row = self._conn.execute(
            f"SELECT {','.join(_NODE_COLS)} FROM nodes"
            " WHERE project=? AND id=?", (project, node_id)
        ).fetchone()
        return _row(_NODE_COLS, row) if row else None

    def _edge_by_id(self, project: str, edge_id: str) -> dict | None:
        row = self._conn.execute(
            f"SELECT {','.join(_EDGE_COLS)} FROM edges"
            " WHERE project=? AND id=?", (project, edge_id)
        ).fetchone()
        return _row(_EDGE_COLS, row) if row else None

    def drop_project(self, project: str) -> dict[str, int]:
        with self._lock:
            n = self._conn.execute(
                "DELETE FROM nodes WHERE project = ?", (project,)).rowcount
            e = self._conn.execute(
                "DELETE FROM edges WHERE project = ?", (project,)).rowcount
            self._conn.commit()
        return {"nodes": n, "edges": e}

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["attrs"] = json.loads(d.get("attrs") or "{}")
    return d
