"""内存图存储 + 可选 zstd/sqlite 持久化。"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Node:
    id: str
    name: str
    label: str
    file_path: str = ""
    qualified_name: str = ""
    start_line: int = 0
    end_line: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    size: float = 1.0
    color: str = ""
    in_calls: int = 0
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    type: str = "CALLS"
    weight: float = 1.0
    attrs: dict[str, Any] = field(default_factory=dict)


class GraphStore:
    """单项目图存储。"""

    def __init__(self, project: str):
        self.project = project
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.meta: dict[str, Any] = {"mode": "moderate", "repo_path": ""}
        self._lock = threading.RLock()
        self._adj_out: dict[str, list[Edge]] = {}
        self._adj_in: dict[str, list[Edge]] = {}
        self._qn_index: dict[str, str] = {}

    def clear(self) -> None:
        with self._lock:
            self.nodes.clear()
            self.edges.clear()
            self._adj_out.clear()
            self._adj_in.clear()
            self._qn_index.clear()

    def add_node(self, node: Node) -> None:
        with self._lock:
            self.nodes[node.id] = node
            if node.qualified_name:
                self._qn_index[node.qualified_name] = node.id
            elif node.name:
                self._qn_index[node.name] = node.id

    def add_edge(self, edge: Edge) -> None:
        with self._lock:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                return
            self.edges.append(edge)
            self._adj_out.setdefault(edge.source, []).append(edge)
            self._adj_in.setdefault(edge.target, []).append(edge)
            self.nodes[edge.target].in_calls += 1

    def rebuild_adj(self) -> None:
        with self._lock:
            self._adj_out.clear()
            self._adj_in.clear()
            for n in self.nodes.values():
                n.in_calls = 0
            for e in self.edges:
                self._adj_out.setdefault(e.source, []).append(e)
                self._adj_in.setdefault(e.target, []).append(e)
                if e.target in self.nodes:
                    self.nodes[e.target].in_calls += 1

    def find_by_qn(self, qn: str) -> Node | None:
        nid = self._qn_index.get(qn)
        if nid:
            return self.nodes.get(nid)
        # 后缀模糊
        for k, nid2 in self._qn_index.items():
            if k.endswith(qn) or qn.endswith(k):
                return self.nodes.get(nid2)
        return None

    def layout_payload(self, max_nodes: int = 5000) -> dict[str, Any]:
        with self._lock:
            nodes = list(self.nodes.values())
            total = len(nodes)
            # 配额：保留结构节点（File/Folder/Module…），避免只剩 Function 导致单色
            structural = [
                n
                for n in nodes
                if n.label in ("File", "Folder", "Module", "Package", "Project", "Section")
            ]
            others = [
                n
                for n in nodes
                if n.label not in ("File", "Folder", "Module", "Package", "Project", "Section")
            ]
            others.sort(key=lambda n: n.in_calls, reverse=True)
            struct_budget = min(len(structural), max(80, max_nodes // 5))
            rest_budget = max(0, max_nodes - struct_budget)
            structural.sort(key=lambda n: n.in_calls, reverse=True)
            picked = structural[:struct_budget] + others[:rest_budget]
            keep = {n.id for n in picked}
            edges = [e for e in self.edges if e.source in keep and e.target in keep]
            return {
                "nodes": [
                    {
                        "id": n.id,
                        "name": n.name,
                        "label": n.label,
                        "x": n.x,
                        "y": n.y,
                        "z": n.z,
                        "file_path": n.file_path,
                        "qualified_name": n.qualified_name or n.name,
                        "start_line": n.start_line,
                        "end_line": n.end_line,
                        "size": n.size,
                        "color": n.color,
                        "in_calls": n.in_calls,
                        **n.attrs,
                    }
                    for n in picked
                ],
                "edges": [
                    {
                        "source": e.source,
                        "target": e.target,
                        "type": e.type,
                        "weight": e.weight,
                    }
                    for e in edges
                ],
                "total_nodes": total,
            }

    def schema(self) -> dict[str, Any]:
        with self._lock:
            labels: dict[str, int] = {}
            etypes: dict[str, int] = {}
            for n in self.nodes.values():
                labels[n.label] = labels.get(n.label, 0) + 1
            for e in self.edges:
                etypes[e.type] = etypes.get(e.type, 0) + 1
            return {
                "node_labels": [{"label": k, "count": v} for k, v in sorted(labels.items())],
                "edge_types": [{"type": k, "count": v} for k, v in sorted(etypes.items())],
            }

    def persist(self, path: Path) -> None:
        """写出可分享的 graph.db（sqlite）；可选 .zst 由调用方压缩。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                "CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)"
            )
            conn.execute(
                "CREATE TABLE nodes (id TEXT PRIMARY KEY, payload TEXT)"
            )
            conn.execute(
                "CREATE TABLE edges (id INTEGER PRIMARY KEY, payload TEXT)"
            )
            with self._lock:
                conn.execute(
                    "INSERT INTO meta VALUES (?, ?)",
                    ("project", self.project),
                )
                conn.execute(
                    "INSERT INTO meta VALUES (?, ?)",
                    ("meta", json.dumps(self.meta, ensure_ascii=False)),
                )
                for n in self.nodes.values():
                    conn.execute(
                        "INSERT INTO nodes VALUES (?, ?)",
                        (
                            n.id,
                            json.dumps(
                                {
                                    "id": n.id,
                                    "name": n.name,
                                    "label": n.label,
                                    "file_path": n.file_path,
                                    "qualified_name": n.qualified_name,
                                    "start_line": n.start_line,
                                    "end_line": n.end_line,
                                    "x": n.x,
                                    "y": n.y,
                                    "z": n.z,
                                    "size": n.size,
                                    "color": n.color,
                                    "in_calls": n.in_calls,
                                    "attrs": n.attrs,
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )
                for i, e in enumerate(self.edges):
                    conn.execute(
                        "INSERT INTO edges VALUES (?, ?)",
                        (
                            i,
                            json.dumps(
                                {
                                    "source": e.source,
                                    "target": e.target,
                                    "type": e.type,
                                    "weight": e.weight,
                                    "attrs": e.attrs,
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    def load(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            self.clear()
            for row in conn.execute("SELECT k, v FROM meta"):
                if row[0] == "meta":
                    self.meta = json.loads(row[1])
            for row in conn.execute("SELECT payload FROM nodes"):
                d = json.loads(row[0])
                self.add_node(
                    Node(
                        id=d["id"],
                        name=d["name"],
                        label=d["label"],
                        file_path=d.get("file_path", ""),
                        qualified_name=d.get("qualified_name", ""),
                        start_line=int(d.get("start_line") or 0),
                        end_line=int(d.get("end_line") or 0),
                        x=float(d.get("x") or 0),
                        y=float(d.get("y") or 0),
                        z=float(d.get("z") or 0),
                        size=float(d.get("size") or 1),
                        color=d.get("color") or "",
                        in_calls=int(d.get("in_calls") or 0),
                        attrs=d.get("attrs") or {},
                    )
                )
            for row in conn.execute("SELECT payload FROM edges"):
                d = json.loads(row[0])
                self.add_edge(
                    Edge(
                        source=d["source"],
                        target=d["target"],
                        type=d.get("type", "CALLS"),
                        weight=float(d.get("weight") or 1),
                        attrs=d.get("attrs") or {},
                    )
                )
            self.rebuild_adj()
        finally:
            conn.close()


def force_layout_3d(
    nodes: list[Node],
    edges: list[Edge],
    *,
    iterations: int = 40,
) -> None:
    """简易 3D 力导向（Python；有 C 扩展时由 layout_c 替换）。

    注意：全量斥力为 O(n²)；节点多时绝不可跑多轮迭代，否则会卡死索引流水线。
    """
    if not nodes:
        return
    n = len(nodes)
    # 初始球面分布
    for i, node in enumerate(nodes):
        if node.x == 0 and node.y == 0 and node.z == 0:
            phi = math.acos(1 - 2 * (i + 0.5) / n)
            theta = math.pi * (1 + 5**0.5) * i
            r = 40.0 + min(n, 500) * 0.05
            node.x = r * math.sin(phi) * math.cos(theta)
            node.y = r * math.sin(phi) * math.sin(theta)
            node.z = r * math.cos(phi)
        node.size = 1.0 + min(8.0, math.log1p(node.in_calls) * 1.5)

    # 大图或 iterations<=0：仅球面初置，交给前端布局
    if iterations <= 0 or n > 500:
        return

    idx = {node.id: i for i, node in enumerate(nodes)}
    for _ in range(iterations):
        fx = [0.0] * n
        fy = [0.0] * n
        fz = [0.0] * n
        # 斥力
        for i in range(n):
            for j in range(i + 1, n):
                dx = nodes[i].x - nodes[j].x
                dy = nodes[i].y - nodes[j].y
                dz = nodes[i].z - nodes[j].z
                dist2 = dx * dx + dy * dy + dz * dz + 0.01
                dist = math.sqrt(dist2)
                force = 80.0 / dist2
                fx[i] += force * dx / dist
                fy[i] += force * dy / dist
                fz[i] += force * dz / dist
                fx[j] -= force * dx / dist
                fy[j] -= force * dy / dist
                fz[j] -= force * dz / dist
        # 边弹簧
        for e in edges:
            i = idx.get(e.source)
            j = idx.get(e.target)
            if i is None or j is None:
                continue
            dx = nodes[j].x - nodes[i].x
            dy = nodes[j].y - nodes[i].y
            dz = nodes[j].z - nodes[i].z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz) + 0.01
            force = (dist - 12.0) * 0.02
            fx[i] += force * dx / dist
            fy[i] += force * dy / dist
            fz[i] += force * dz / dist
            fx[j] -= force * dx / dist
            fy[j] -= force * dy / dist
            fz[j] -= force * dz / dist
        # 向心
        for i, node in enumerate(nodes):
            fx[i] -= node.x * 0.01
            fy[i] -= node.y * 0.01
            fz[i] -= node.z * 0.01
            node.x += max(-2.0, min(2.0, fx[i]))
            node.y += max(-2.0, min(2.0, fy[i]))
            node.z += max(-2.0, min(2.0, fz[i]))
            node.size = 1.0 + min(8.0, math.log1p(node.in_calls) * 1.5)
