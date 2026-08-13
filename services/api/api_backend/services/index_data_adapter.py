"""引擎 layout/响应 → Voyager 统一图契约。"""
from __future__ import annotations

from typing import Any

from api_backend.schemas.graph import (
    CodeGraphEdge,
    CodeGraphNode,
    GraphStats,
    UnifiedGraphData,
)


def adapt_layout(raw: dict[str, Any], *, level: str = "code") -> UnifiedGraphData:
    """将 GET /api/layout 响应映射为 UnifiedGraphData。"""
    nodes_out: list[CodeGraphNode] = []
    for n in raw.get("nodes") or []:
        nid = n.get("id")
        nodes_out.append(
            CodeGraphNode(
                id=str(nid),
                name=str(n.get("name") or n.get("label") or nid),
                kind=str(n.get("label") or "Unknown"),
                level=level,  # type: ignore[arg-type]
                x=_f(n.get("x")),
                y=_f(n.get("y")),
                z=_f(n.get("z")),
                file_path=n.get("file_path"),
                qualified_name=n.get("qualified_name"),
                start_line=_i(n.get("start_line")),
                end_line=_i(n.get("end_line")),
                size=_f(n.get("size")),
                color=n.get("color"),
                status=n.get("status"),
                in_calls=_i(n.get("in_calls")),
                attrs={
                    k: v
                    for k, v in n.items()
                    if k
                    not in {
                        "id",
                        "name",
                        "label",
                        "x",
                        "y",
                        "z",
                        "file_path",
                        "qualified_name",
                        "start_line",
                        "end_line",
                        "size",
                        "color",
                        "status",
                        "in_calls",
                    }
                },
            )
        )

    edges_out: list[CodeGraphEdge] = []
    for e in raw.get("edges") or []:
        edges_out.append(
            CodeGraphEdge(
                source=str(e.get("source")),
                target=str(e.get("target")),
                relation=str(e.get("type") or e.get("relation") or "RELATED"),
            )
        )

    total = raw.get("total_nodes")
    stats = GraphStats(
        node_count=len(nodes_out),
        edge_count=len(edges_out),
        total_nodes=int(total) if total is not None else len(nodes_out),
    )
    return UnifiedGraphData(nodes=nodes_out, edges=edges_out, stats=stats)


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
