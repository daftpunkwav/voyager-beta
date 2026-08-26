"""GraphEngine 极简 Cypher 子集(C2 拆分:查询职责 mixin)。

支持 MATCH (n:Label) / MATCH (a)-[r:TYPE]->(b) + WHERE/RETURN/LIMIT;
WHERE n.x 求值走白名单字段,不做 getattr 动态访问。
"""
from __future__ import annotations

import re
from typing import Any

_CYPHER_ROW_CAP = 100_000

#: WHERE n.x = '...' 允许直读的节点字段;其余属性名一律落到 attrs
_NODE_WHERE_FIELDS = frozenset({"id", "name", "label", "qualified_name", "file_path"})


class QueryMixin:
    """Cypher 子集查询(self 为 GraphEngine,用 _store/_cross_edges)。"""

    def query_graph(
        self, project: str, query: str, *, limit: int = _CYPHER_ROW_CAP
    ) -> dict[str, Any]:
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
            # 合并跨仓边（供 L0 投影）
            if etype is None or (etype or "").startswith("CROSS") or (
                where and "CROSS_" in (where or "").upper()
            ):
                for ce in self._cross_edges:
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


def _eval_where_node(n, where: str) -> bool:
    w = where.strip()
    m = re.match(r"n\.(\w+)\s*=\s*['\"](.+)['\"]", w, re.IGNORECASE)
    if m:
        attr, val = m.group(1), m.group(2)
        if attr in _NODE_WHERE_FIELDS:
            return str(getattr(n, attr, "")) == val
        return str((n.attrs or {}).get(attr, "")) == val
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
    if ret == var:
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
