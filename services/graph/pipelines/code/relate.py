"""程序化管线·仓库关联度分析(§8.4):跨仓库依赖/相似边。

修订自旧 fallback 引擎的 _cross_repo:相同 import 目标/相同技术栈
产生 CROSS_REPO 边,写入规范存储(source="code")。当前引擎能力范围
仅覆盖源码级关联;语义级相似(嵌入)是未来演进。
"""

from __future__ import annotations

from typing import Any

from store import GraphStore

_EXTERNAL_HINTS = ("fastapi", "django", "flask", "react", "vue", "sqlalchemy",
                   "pydantic", "numpy", "pandas", "httpx", "click", "rich")


def relate_repos(store: GraphStore, projects: list[str]) -> dict[str, Any]:
    """两两仓库:共享外部依赖/技术栈 → CROSS_REPO 边(upsert 幂等)。"""
    created = 0
    deps_by_project = {p: _external_deps(store, p) for p in projects}
    node_ids = {
        p: store.upsert_node("cross-repo", "Project", p, p,
                             source="code", actor="pipeline.relate")["id"]
        for p in projects
    }
    for i, a in enumerate(projects):
        for b in projects[i + 1:]:
            shared = sorted(deps_by_project[a] & deps_by_project[b])
            if not shared:
                continue
            for dep in shared:
                store.upsert_edge(
                    "cross-repo", node_ids[a], node_ids[b], "CROSS_REPO",
                    {"shared_dependency": dep}, source="code", actor="pipeline.relate",
                )
                created += 1
    return {"projects": projects, "cross_edges": created,
            "shared": {f"{a}~{b}": sorted(deps_by_project[a] & deps_by_project[b])
                       for i, a in enumerate(projects) for b in projects[i + 1:]
                       if deps_by_project[a] & deps_by_project[b]}}


def _external_deps(store: GraphStore, project: str) -> set[str]:
    graph = store.query(project, limit=100000)
    deps: set[str] = set()
    for node in graph["nodes"]:
        target = str(node["attrs"].get("import_target") or "")
        root = target.split(".")[0].lower()
        if root in _EXTERNAL_HINTS:
            deps.add(root)
    return deps
