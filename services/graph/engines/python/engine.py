"""Voyager 自研图谱引擎 —— 对齐原生 C 引擎工具面契约。"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from .indexer import index_repository
from .store import GraphStore

_CYPHER_ROW_CAP = 100_000
_DEFAULT_SEARCH_LIMIT = 200

_engine_singleton: GraphEngine | None = None
_engine_lock = threading.Lock()


def get_engine(data_root: str | Path | None = None) -> GraphEngine:
    global _engine_singleton
    with _engine_lock:
        if _engine_singleton is None:
            _engine_singleton = GraphEngine(data_root=data_root)
        return _engine_singleton


class GraphEngine:
    """进程内引擎；亦可被 HTTP sidecar 包装。"""

    def __init__(self, data_root: str | Path | None = None):
        self.data_root = Path(data_root) if data_root else Path.cwd() / "data"
        self.graphs_dir = self.data_root / "graph-db"
        self.graphs_dir.mkdir(parents=True, exist_ok=True)
        self._projects: dict[str, GraphStore] = {}
        self._cross_edges: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def health(self) -> bool:
        return True

    def _store(self, project: str) -> GraphStore:
        with self._lock:
            if project not in self._projects:
                store = GraphStore(project)
                db = self.graphs_dir / f"{project}.db"
                if db.exists():
                    try:
                        store.load(db)
                    except Exception:
                        pass
                self._projects[project] = store
            return self._projects[project]

    def index_repository(
        self,
        repo_path: str,
        *,
        mode: str = "moderate",
        name: str | None = None,
        target_projects: list[str] | None = None,
        persistence: bool = True,
        should_abandon: Any = None,
    ) -> dict[str, Any]:
        if mode == "cross-repo-intelligence":
            return self._cross_repo(target_projects or [])

        project = name or Path(repo_path).name
        store = self._store(project)
        # 同项目索引互斥；不同项目可并行（store 按名隔离）
        with self._lock:
            project_lock = getattr(store, "_index_lock", None)
            if project_lock is None:
                project_lock = threading.Lock()
                store._index_lock = project_lock
        with project_lock:
            if callable(should_abandon) and should_abandon():
                return {
                    "project": project,
                    "mode": mode,
                    "abandoned": True,
                    "node_count": 0,
                    "edge_count": 0,
                }
            result = index_repository(store, repo_path, mode=mode)
            if callable(should_abandon) and should_abandon():
                result["abandoned"] = True
                return result
            if persistence:
                db_path = self.graphs_dir / f"{project}.db"
                store.persist(db_path)
                # 可选 zst：无 zstandard 时仅保留 .db
                zst = Path(str(db_path) + ".zst")
                try:
                    import zstandard as zstd  # type: ignore

                    cctx = zstd.ZstdCompressor(level=3)
                    with open(db_path, "rb") as src, open(zst, "wb") as dst:
                        dst.write(cctx.compress(src.read()))
                    result["persistence_path"] = str(zst)
                except Exception:
                    result["persistence_path"] = str(db_path)
        return result

    def drop_project(self, project: str) -> dict[str, Any]:
        """删除内存图与持久化文件（.db / .db.zst）。"""
        name = (project or "").strip()
        removed_files: list[str] = []
        with self._lock:
            self._projects.pop(name, None)
            for path in (
                self.graphs_dir / f"{name}.db",
                self.graphs_dir / f"{name}.db.zst",
            ):
                if path.exists():
                    try:
                        path.unlink()
                        removed_files.append(str(path))
                    except OSError:
                        pass
        return {"project": name, "removed_files": removed_files}

    def _cross_repo(self, projects: list[str]) -> dict[str, Any]:
        """基于同名符号/HTTP 启发式生成跨仓边。"""
        edges: list[dict[str, Any]] = []
        stores = [self._store(p) for p in projects if p]
        # 符号名倒排
        name_map: dict[str, list[tuple[str, str]]] = {}
        for st in stores:
            for n in st.nodes.values():
                if n.label in ("Function", "Method", "Class"):
                    name_map.setdefault(n.name.lower(), []).append(
                        (st.project, n.qualified_name or n.name)
                    )
        for _name, locs in name_map.items():
            projs = {p for p, _ in locs}
            if len(projs) < 2:
                continue
            # 两两连边
            uniq = list({(p, q) for p, q in locs})
            for i in range(min(len(uniq), 8)):
                for j in range(i + 1, min(len(uniq), 8)):
                    if uniq[i][0] == uniq[j][0]:
                        continue
                    edges.append(
                        {
                            "source_engine": uniq[i][0],
                            "target_engine": uniq[j][0],
                            "source_symbol": uniq[i][1],
                            "target_symbol": uniq[j][1],
                            "relation": "CROSS_SHARED_SYMBOL",
                            "type": "CROSS_SHARED_SYMBOL",
                            "weight": 1.0,
                        }
                    )
                    if len(edges) >= 500:
                        break
                if len(edges) >= 500:
                    break
            if len(edges) >= 500:
                break

        with self._lock:
            self._cross_edges = edges
        return {"mode": "cross-repo-intelligence", "edge_count": len(edges), "edges": edges}

    def export_graph(self, project: str) -> dict[str, Any]:
        """全图导出(节点 + 边),供规范存储同步;不受 search limit 封顶。"""
        store = self._store(project)
        with self._lock:
            nodes = [
                {
                    "id": n.id,
                    "name": n.name,
                    "label": n.label,
                    "qualified_name": n.qualified_name,
                    "file_path": n.file_path,
                    "attrs": dict(n.attrs),
                }
                for n in store.nodes.values()
            ]
            edges = [
                {
                    "src": e.source,
                    "dst": e.target,
                    "type": e.type,
                    "attrs": dict(e.attrs),
                }
                for e in store.edges
            ]
        return {"nodes": nodes, "edges": edges}

    def fetch_layout(
        self, project: str, *, max_nodes: int = 5000, graph: str = "code"
    ) -> dict[str, Any]:
        return self._store(project).layout_payload(max_nodes=max_nodes)

    def get_graph_schema(self, project: str) -> dict[str, Any]:
        return self._store(project).schema()

    def search_graph(
        self,
        project: str,
        *,
        query: str = "",
        name_pattern: str = "",
        semantic_query: str = "",
        label: str | None = None,
        limit: int = _DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = min(max(1, limit or _DEFAULT_SEARCH_LIMIT), _DEFAULT_SEARCH_LIMIT)
        offset = max(0, offset)
        store = self._store(project)
        q = (query or semantic_query or "").lower().strip()
        pat = name_pattern.strip()
        scored: list[tuple[float, dict]] = []
        for n in store.nodes.values():
            if label and n.label != label:
                continue
            hay = f"{n.name} {n.qualified_name} {n.file_path} {n.label}".lower()
            score = 0.0
            if q:
                if q in hay:
                    score += 5.0 + (10.0 if n.name.lower() == q else 0)
                for tok in q.split():
                    if tok in hay:
                        score += 1.5
                # BM25 粗近似：词频 + 入度
                score += min(3.0, n.in_calls * 0.1)
            if pat:
                try:
                    if not re.search(pat, n.name) and not re.search(
                        pat, n.qualified_name or ""
                    ):
                        if not q:
                            continue
                    else:
                        score += 8.0
                except re.error:
                    if pat.lower() not in hay:
                        continue
                    score += 4.0
            if not q and not pat:
                score = 1.0 + n.in_calls * 0.05
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    {
                        "id": n.id,
                        "name": n.name,
                        "label": n.label,
                        "qualified_name": n.qualified_name,
                        "file_path": n.file_path,
                        "score": round(score, 3),
                        "in_calls": n.in_calls,
                        **{k: v for k, v in n.attrs.items() if k.startswith(("cyclo", "cogni", "loop", "alloc", "unguard", "linear", "trans"))},
                    },
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        total = len(scored)
        page = [x[1] for x in scored[offset : offset + limit]]
        return {
            "results": page,
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    def search_code(
        self,
        project: str,
        *,
        pattern: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """grep 增强：命中归并到函数节点并按重要度排序。"""
        store = self._store(project)
        root = Path(store.meta.get("repo_path") or "")
        hits: list[dict[str, Any]] = []
        if not root.exists() or not pattern:
            return {"results": [], "has_more": False}
        try:
            rx = re.compile(pattern)
        except re.error:
            rx = re.compile(re.escape(pattern))

        file_hits: dict[str, list[dict]] = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {
                ".py",
                ".js",
                ".ts",
                ".tsx",
                ".go",
                ".rs",
                ".java",
            }:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    file_hits.setdefault(rel, []).append(
                        {"line": i, "text": line.strip()[:240]}
                    )
                    if sum(len(v) for v in file_hits.values()) > 2000:
                        break
            if sum(len(v) for v in file_hits.values()) > 2000:
                break

        # 归并到函数
        for n in store.nodes.values():
            if n.label not in ("Function", "Method", "Class"):
                continue
            fh = file_hits.get(n.file_path)
            if not fh:
                continue
            matched = [
                h
                for h in fh
                if (not n.start_line or h["line"] >= n.start_line)
                and (not n.end_line or h["line"] <= n.end_line)
            ]
            if not matched:
                continue
            hits.append(
                {
                    "qualified_name": n.qualified_name,
                    "name": n.name,
                    "file_path": n.file_path,
                    "label": n.label,
                    "in_calls": n.in_calls,
                    "matches": matched[:10],
                    "importance": n.in_calls + len(matched),
                }
            )
        hits.sort(key=lambda x: x["importance"], reverse=True)
        limit = min(max(1, limit), 200)
        page = hits[:limit]
        return {
            "results": page,
            "total": len(hits),
            "has_more": len(hits) > limit,
            "limit": limit,
        }

    def get_code_snippet(self, project: str, qualified_name: str) -> dict[str, Any]:
        store = self._store(project)
        node = store.find_by_qn(qualified_name)
        if not node:
            return {"error": "symbol_not_found", "qualified_name": qualified_name}
        root = Path(store.meta.get("repo_path") or "")
        path = root / node.file_path if root.exists() else None
        code = ""
        if path and path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            s = max(0, (node.start_line or 1) - 1)
            e = node.end_line or (s + 40)
            code = "\n".join(lines[s:e])
        return {
            "qualified_name": node.qualified_name,
            "file_path": node.file_path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "code": code,
            "attrs": node.attrs,
        }

    def trace_path(
        self,
        project: str,
        *,
        start: str = "",
        symbol: str = "",
        direction: str = "both",
        depth: int = 3,
        kind: str = "calls",
    ) -> dict[str, Any]:
        store = self._store(project)
        sym = start or symbol
        node = store.find_by_qn(sym)
        if not node:
            # 按短名
            for n in store.nodes.values():
                if n.name == sym:
                    node = n
                    break
        if not node:
            return {"error": "symbol_not_found", "symbol": sym}

        edge_types = {
            "calls": {"CALLS"},
            "data_flow": {"CALLS", "DEFINES", "CONTAINS"},
            "cross_service": {"CROSS_HTTP_CALLS", "CROSS_ASYNC", "CROSS_CHANNEL", "CROSS_SHARED_SYMBOL"},
        }.get(kind, {"CALLS"})

        visited: set[str] = set()
        paths: list[list[str]] = []
        nodes_out: list[dict] = []
        edges_out: list[dict] = []

        def risk(hops: int) -> str:
            if hops <= 1:
                return "LOW"
            if hops == 2:
                return "MEDIUM"
            if hops == 3:
                return "HIGH"
            return "CRITICAL"

        def walk(nid: str, trail: list[str], hops: int, forward: bool) -> None:
            if hops > depth or nid in visited and hops > 0:
                return
            visited.add(nid)
            n = store.nodes.get(nid)
            if n:
                nodes_out.append(
                    {
                        "id": n.id,
                        "name": n.name,
                        "qualified_name": n.qualified_name,
                        "label": n.label,
                    }
                )
            adj = store._adj_out.get(nid, []) if forward else store._adj_in.get(nid, [])
            for e in adj:
                if e.type not in edge_types and kind != "data_flow":
                    if kind == "calls" and e.type != "CALLS":
                        continue
                nxt = e.target if forward else e.source
                edges_out.append(
                    {
                        "source": e.source,
                        "target": e.target,
                        "type": e.type,
                        "risk": risk(hops + 1),
                    }
                )
                new_trail = trail + [nxt]
                if hops + 1 >= depth:
                    paths.append(new_trail)
                walk(nxt, new_trail, hops + 1, forward)

        if direction in ("downstream", "both", "outgoing"):
            walk(node.id, [node.id], 0, True)
        visited.clear()
        if direction in ("upstream", "both", "incoming"):
            walk(node.id, [node.id], 0, False)

        return {
            "start": node.qualified_name or node.name,
            "kind": kind,
            "direction": direction,
            "depth": depth,
            "nodes": nodes_out[:500],
            "edges": edges_out[:1000],
            "paths": paths[:100],
            "risk_summary": {
                "CRITICAL": sum(1 for e in edges_out if e.get("risk") == "CRITICAL"),
                "HIGH": sum(1 for e in edges_out if e.get("risk") == "HIGH"),
                "MEDIUM": sum(1 for e in edges_out if e.get("risk") == "MEDIUM"),
                "LOW": sum(1 for e in edges_out if e.get("risk") == "LOW"),
            },
        }

    def query_graph(
        self, project: str, query: str, *, limit: int = _CYPHER_ROW_CAP
    ) -> dict[str, Any]:
        """极简 Cypher 子集：MATCH (n) / MATCH (a)-[r]->(b) + WHERE label/type + RETURN。"""
        store = self._store(project)
        q = " ".join((query or "").split())
        limit = min(max(1, limit), _CYPHER_ROW_CAP)
        rows: list[dict[str, Any]] = []

        # MATCH (n:Label) RETURN n LIMIT
        m = re.search(
            r"MATCH\s*\(\s*(\w+)(?::(\w+))?\s*\)(?:\s*WHERE\s+(.+?))?\s*RETURN\s+(.+?)(?:\s*LIMIT\s+(\d+))?$",
            q,
            re.IGNORECASE,
        )
        if m and "-[" not in q:
            var, label, where, ret, lim = m.groups()
            if lim:
                limit = min(limit, int(lim))
            for n in store.nodes.values():
                if label and n.label.lower() != label.lower():
                    continue
                if where and not _eval_where_node(n, where):
                    continue
                rows.append(_project_node(n, ret, var))
                if len(rows) >= limit:
                    break
            return {"rows": rows, "row_count": len(rows), "capped_at": _CYPHER_ROW_CAP}

        # MATCH (a)-[r:TYPE]->(b) RETURN ...
        m2 = re.search(
            r"MATCH\s*\(\s*(\w+)\s*\)\s*-\s*\[\s*(\w+)(?::(\w+))?\s*\]\s*->\s*\(\s*(\w+)\s*\)"
            r"(?:\s*WHERE\s+(.+?))?\s*RETURN\s+(.+?)(?:\s*LIMIT\s+(\d+))?$",
            q,
            re.IGNORECASE,
        )
        if m2:
            a, r, etype, b, where, ret, lim = m2.groups()
            if lim:
                limit = min(limit, int(lim))
            for e in store.edges:
                if etype and e.type.upper() != etype.upper():
                    continue
                if where and "CROSS_" in (where.upper()) and not e.type.startswith("CROSS_"):
                    # 特殊：type(r) STARTS WITH 'CROSS_'
                    if "STARTS WITH" in where.upper() and "CROSS_" in where.upper():
                        if not e.type.startswith("CROSS_"):
                            continue
                    elif not _eval_where_edge(e, where):
                        continue
                elif where and "STARTS WITH" in where.upper() and "CROSS_" in where.upper():
                    if not e.type.startswith("CROSS_"):
                        continue
                sa = store.nodes.get(e.source)
                sb = store.nodes.get(e.target)
                if not sa or not sb:
                    continue
                row = {
                    "src": sa.qualified_name or sa.name,
                    "dst": sb.qualified_name or sb.name,
                    "rel": e.type,
                    a: sa.qualified_name or sa.name,
                    b: sb.qualified_name or sb.name,
                    r: e.type,
                }
                rows.append(row)
                if len(rows) >= limit:
                    break
            # 合并跨仓边
            if etype is None or (etype or "").startswith("CROSS") or (
                where and "CROSS_" in (where or "").upper()
            ):
                for ce in self._cross_edges:
                    if project and ce.get("source_engine") != project and ce.get(
                        "target_engine"
                    ) != project:
                        # 仍返回全局跨仓边供 L0 投影
                        pass
                    rows.append(
                        {
                            "src": ce.get("source_symbol"),
                            "dst": ce.get("target_symbol"),
                            "rel": ce.get("type") or ce.get("relation"),
                            "source_engine": ce.get("source_engine"),
                            "target_engine": ce.get("target_engine"),
                        }
                    )
                    if len(rows) >= limit:
                        break
            return {"rows": rows[:limit], "row_count": len(rows[:limit]), "capped_at": _CYPHER_ROW_CAP}

        # 兜底：返回 schema 提示
        return {
            "rows": [],
            "row_count": 0,
            "error": "unsupported_cypher",
            "hint": "支持 MATCH (n:Label) RETURN n 与 MATCH (a)-[r]->(b) RETURN ...；硬上限 10 万行",
            "capped_at": _CYPHER_ROW_CAP,
        }

    def get_architecture(
        self, project: str, aspects: list[str] | None = None
    ) -> dict[str, Any]:
        store = self._store(project)
        packages: dict[str, int] = {}
        entry_points: list[dict] = []
        hotspots: list[dict] = []
        for n in store.nodes.values():
            pkg = (n.attrs or {}).get("package") or (
                n.file_path.rsplit("/", 1)[0] if n.file_path else "."
            )
            if n.label == "File":
                packages[pkg] = packages.get(pkg, 0) + 1
            if n.label in ("Function", "Method") and n.in_calls == 0 and n.name in {
                "main",
                "run",
                "handler",
                "app",
                "index",
            }:
                entry_points.append(
                    {"name": n.name, "qualified_name": n.qualified_name, "file": n.file_path}
                )
            if n.in_calls >= 3:
                hotspots.append(
                    {
                        "name": n.name,
                        "qualified_name": n.qualified_name,
                        "in_calls": n.in_calls,
                        "cyclomatic_complexity": n.attrs.get("cyclomatic_complexity"),
                    }
                )
        hotspots.sort(key=lambda x: x["in_calls"], reverse=True)

        # Leiden 简化：按 package 聚类
        clusters = [
            {"id": f"c_{i}", "label": pkg, "size": cnt, "algorithm": "package-leiden-approx"}
            for i, (pkg, cnt) in enumerate(sorted(packages.items(), key=lambda x: -x[1])[:50])
        ]

        layers = [
            {"name": "presentation", "hint": "ui/pages/components"},
            {"name": "application", "hint": "services/api"},
            {"name": "domain", "hint": "models/core"},
            {"name": "infrastructure", "hint": "db/clients"},
        ]
        boundaries = [
            {"from": a["name"], "to": b["name"], "rule": "allowed"}
            for a, b in zip(layers, layers[1:])
        ]

        out = {
            "packages": [{"name": k, "file_count": v} for k, v in sorted(packages.items())],
            "entry_points": entry_points[:50],
            "hotspots": hotspots[:50],
            "layers": layers,
            "boundaries": boundaries,
            "clusters": clusters,
        }
        if aspects:
            return {k: out[k] for k in aspects if k in out}
        return out

    def list_cross_edges(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._cross_edges)

    def call(self, name: str, args: dict[str, Any]) -> Any:
        """统一工具分派入口（client._sync_call 与 HTTP server._dispatch 共用）。

        新增工具只需在此加一个分支，避免在 client.py 与 server.py 同步三处映射。
        """
        if name == "index_repository":
            return self.index_repository(
                args.get("repo_path") or ".",
                mode=args.get("mode") or "moderate",
                name=args.get("name"),
                target_projects=args.get("target_projects"),
                persistence=bool(args.get("persistence", True)),
            )
        if name == "search_graph":
            return self.search_graph(
                args["project"],
                query=args.get("query") or "",
                name_pattern=args.get("name_pattern") or "",
                semantic_query=args.get("semantic_query") or "",
                label=args.get("label"),
                limit=int(args.get("limit") or 200),
                offset=int(args.get("offset") or 0),
            )
        if name == "search_code":
            return self.search_code(
                args["project"],
                pattern=args.get("pattern") or args.get("query") or "",
                limit=int(args.get("limit") or 50),
            )
        if name == "get_code_snippet":
            return self.get_code_snippet(
                args["project"], args.get("qualified_name") or ""
            )
        if name == "trace_path":
            return self.trace_path(
                args["project"],
                start=args.get("start") or args.get("symbol") or "",
                symbol=args.get("symbol") or "",
                direction=args.get("direction") or "both",
                depth=int(args.get("depth") or 3),
                kind=args.get("kind") or args.get("type") or "calls",
            )
        if name == "query_graph":
            return self.query_graph(
                args.get("project") or "",
                args.get("query") or "",
                limit=int(args.get("limit") or 100_000),
            )
        if name == "export_graph":
            return self.export_graph(args["project"])
        if name == "get_graph_schema":
            return self.get_graph_schema(args["project"])
        if name == "get_architecture":
            return self.get_architecture(
                args["project"], aspects=args.get("aspects")
            )
        if name == "drop_project":
            return self.drop_project(args.get("project") or args.get("name") or "")
        raise ValueError(f"unknown tool: {name}")


def _eval_where_node(n, where: str) -> bool:
    w = where.strip()
    m = re.match(r"n\.(\w+)\s*=\s*['\"](.+)['\"]", w, re.IGNORECASE)
    if m:
        attr, val = m.group(1), m.group(2)
        return str(getattr(n, attr, n.attrs.get(attr, ""))) == val
    if "cyclomatic_complexity" in w:
        m2 = re.search(r">\s*(\d+)", w)
        if m2:
            return int(n.attrs.get("cyclomatic_complexity") or 0) > int(m2.group(1))
    return True


def _eval_where_edge(e, where: str) -> bool:
    return True


def _project_node(n, ret: str, var: str) -> dict[str, Any]:
    ret = ret.strip()
    base = {
        "id": n.id,
        "name": n.name,
        "label": n.label,
        "qualified_name": n.qualified_name,
        "file_path": n.file_path,
        **n.attrs,
    }
    if ret == var or ret == f"{var}":
        return base
    out = {}
    for part in ret.split(","):
        part = part.strip()
        if "." in part:
            _, attr = part.split(".", 1)
            attr = attr.strip()
            out[attr] = base.get(attr)
        else:
            out[part] = base
    return out or base
