"""内置 Agent 工具实现"""
from __future__ import annotations

import logging
import re
import threading  # §4.2.6 ensure_tools_loaded 锁
from typing import Any
from uuid import UUID

from py_shared.models.project import Project

from agent_core.tools.registry import tool

logger = logging.getLogger(__name__)


def _ports(context):
    """优先用注入的 ToolPorts；测试兜底从 db 构建。"""
    ports = getattr(context, "ports", None)
    if ports is not None:
        return ports
    from api_backend.ports.sqlalchemy_adapters import build_tool_ports

    return build_tool_ports(context.db)


_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def _safe_github_name(value: str) -> str | None:
    """拒绝路径穿越与异常字符，降低 GitHub API path 注入风险。

    §4.2.5: 在白名单基础上追加 URL 编码往返校验，防御 %2e%2e / %2f 等编码绕过。
    """
    s = (value or "").strip().removesuffix(".git")
    if not s or "/" in s or "\\" in s or ".." in s:
        return None
    if not _GITHUB_NAME_RE.fullmatch(s):
        return None
    # 二次校验：URL 编码后再解码应与原值一致
    from urllib.parse import quote, unquote
    if unquote(quote(s, safe="")) != s:
        return None
    return s


def _parse_owner_repo(
    *,
    owner: str = "",
    repo: str = "",
    full_name: str = "",
    fallback_url: str | None = None,
) -> tuple[str | None, str | None]:
    o, r = owner, repo
    if full_name and "/" in full_name:
        parts = full_name.split("/")
        if len(parts) == 2:
            o, r = parts[0], parts[1]
        else:
            return None, None
    if (not o or not r) and fallback_url:
        m = re.search(r"github\.com/([^/]+)/([^/#?]+)", fallback_url)
        if m:
            o, r = m.group(1), m.group(2).removesuffix(".git")
    so, sr = _safe_github_name(o or ""), _safe_github_name(r or "")
    if not so or not sr:
        return None, None
    return so, sr


@tool(
    name="query_user_projects",
    description="查询用户项目库。支持按名称、分类、语言、学习进度筛选。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "language": {"type": "string"},
            "progress": {
                "type": "string",
                "enum": ["none", "learning", "learned", "mastered"],
            },
            "limit": {"type": "integer", "default": 20},
        },
    },
    allowed_agents=["scout", "mentor", "navigator", "curator", "scribe", "hub", "atlas"],
    timeout_ms=10_000,
)
async def query_user_projects(
    context=None,
    query: str = "",
    language: str = "",
    progress: str = "",
    limit: int = 20,
    **kw,
):
    rows = await _ports(context).projects.search(
                query=query or "",
        language=language or "",
        progress=progress or "",
        limit=min(limit or 20, 50),
    )
    return {
        "count": len(rows),
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "url": p.url,
                "language": p.language,
                "stars": p.stars,
                "progress": p.progress,
                "description": (p.description or "")[:200],
                "category_id": str(p.category_id) if p.category_id else None,
            }
            for p in rows
        ],
    }


def _project_detail_payload(p: Project) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "url": p.url,
        "language": p.language,
        "stars": p.stars,
        "progress": p.progress,
        "description": p.description,
        "note": p.note,
        "source": p.source,
        "category_id": str(p.category_id) if p.category_id else None,
    }


@tool(
    name="get_project_detail",
    description=(
        "获取用户项目库中单个项目的详细信息。"
        "project_id 必须是 UUID；若只有 owner/repo，请改用 fetch_github_repo / fetch_readme。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "项目 UUID（勿传 owner/repo）",
            }
        },
        "required": ["project_id"],
    },
    allowed_agents=["scout", "mentor", "navigator", "curator", "scribe", "hub", "atlas"],
)
async def get_project_detail(project_id: str, context=None, **kw):
    raw = str(project_id or "").strip()
    if not raw:
        return {"error": "无效 project_id"}

    ports = _ports(context)
    try:
        pid = UUID(raw)
    except ValueError:
        # 兼容误把 owner/repo 当 id：仅在用户库内按 name 回退
        owner, repo = _parse_owner_repo(full_name=raw)
        if owner and repo:
            full_name = f"{owner}/{repo}"
            p = await ports.projects.get_by_name(full_name)
            if p:
                return _project_detail_payload(p)
            return {
                "error": "无效 project_id",
                "hint": (
                    "project_id 须为 UUID；库外仓库请改用 fetch_github_repo / fetch_readme，"
                    f"参数 full_name={full_name}"
                ),
                "full_name": full_name,
            }
        return {
            "error": "无效 project_id",
            "hint": "project_id 须为 UUID；库外仓库用 fetch_github_repo / fetch_readme 的 full_name",
        }

    p = await ports.projects.get_owned(pid)
    if not p:
        return {"error": "项目不存在"}
    return _project_detail_payload(p)


@tool(
    name="fetch_github_repo",
    description=(
        "通过 GitHub API 获取公开仓库元数据。"
        "库外速览请用本工具；勿把 owner/repo 传给 get_project_detail。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "full_name": {
                "type": "string",
                "description": "形如 owner/repo，可替代 owner+repo",
            },
        },
    },
    allowed_agents=["scout", "mentor", "curator", "hub", "navigator"],
    timeout_ms=15_000,
)
async def fetch_github_repo(
    context=None,
    owner: str = "",
    repo: str = "",
    full_name: str = "",
    **kw,
):
    fallback = (
        context.project.url
        if context and getattr(context, "project", None) and context.project.url
        else None
    )
    owner, repo = _parse_owner_repo(
        owner=owner, repo=repo, full_name=full_name, fallback_url=fallback
    )
    if not owner or not repo:
        return {"error": "需要合法的 owner/repo"}
    from agent_core import services as _agent_svc

    return await _agent_svc.github().fetch_repo_info(owner, repo)


@tool(
    name="fetch_readme",
    description=(
        "获取 GitHub 仓库 README 文本（截断）。"
        "用 full_name=owner/repo 或 owner+repo；不要用 project_id。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "full_name": {
                "type": "string",
                "description": "形如 owner/repo",
            },
            "max_chars": {"type": "integer", "default": 6000},
        },
    },
    allowed_agents=["scout", "mentor", "scribe", "curator"],
    timeout_ms=15_000,
)
async def fetch_readme(
    context=None,
    owner: str = "",
    repo: str = "",
    full_name: str = "",
    max_chars: int = 6000,
    **kw,
):
    fallback = (
        context.project.url
        if context and getattr(context, "project", None) and context.project.url
        else None
    )
    owner, repo = _parse_owner_repo(
        owner=owner, repo=repo, full_name=full_name, fallback_url=fallback
    )
    if not owner or not repo:
        return {"error": "需要合法的 owner/repo"}
    from agent_core import services as _agent_svc

    text = await _agent_svc.github().fetch_readme_text(owner, repo)
    if text is None:
        return {"error": "无法获取 README", "owner": owner, "repo": repo}
    return {
        "owner": owner,
        "repo": repo,
        "readme": text[: max_chars or 6000],
        "truncated": len(text) > (max_chars or 6000),
    }


@tool(
    name="query_knowledge_graph",
    description="查询用户项目知识图谱：相似项目、关联边。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "中心项目，可选"},
            "min_similarity": {"type": "number", "default": 0.3},
            "limit": {"type": "integer", "default": 20},
        },
    },
    allowed_agents=["scout", "mentor", "navigator", "scribe", "atlas", "hub"],
)
async def query_knowledge_graph(
    context=None,
    project_id: str = "",
    min_similarity: float = 0.3,
    limit: int = 20,
    **kw,
):
    graph = await _ports(context).graph.build(
                min_similarity=min_similarity,
        max_edges=limit or 20,
    )
    if project_id:
        edges = [
            e
            for e in graph["edges"]
            if e["source"] == project_id or e["target"] == project_id
        ]
        node_ids = {project_id}
        for e in edges:
            node_ids.add(e["source"])
            node_ids.add(e["target"])
        nodes = [n for n in graph["nodes"] if n["id"] in node_ids]
        return {"nodes": nodes, "edges": edges}
    return {
        "nodes": graph["nodes"][:50],
        "edges": graph["edges"][: limit or 20],
    }


@tool(
    name="trigger_code_index",
    description="触发项目代码图谱索引（浅克隆 + Voyager 自研引擎）。返回索引状态。学习场景请先索引再 search/architecture/trace。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "mode": {
                "type": "string",
                "enum": ["fast", "moderate", "full", "cross-repo-intelligence"],
                "default": "moderate",
            },
        },
        "required": ["project_id"],
    },
    allowed_agents=["atlas", "hub", "scout", "navigator"],
)
async def trigger_code_index(
    context=None,
    project_id: str = "",
    mode: str = "moderate",
    **kw,
):
    from graph_engine_runtime import index_pipeline as pipeline

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id"}
    return await pipeline.trigger_index(context.db, pid, mode=mode or "moderate")


@tool(
    name="search_code_graph",
    description="在已索引代码图谱中搜索符号（search_graph：BM25+结构加权）。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "query": {"type": "string"},
            "name_pattern": {"type": "string"},
            "semantic_query": {"type": "string"},
            "label": {"type": "string"},
            "limit": {"type": "integer", "default": 200},
            "offset": {"type": "integer", "default": 0},
        },
        "required": ["project_id"],
    },
    allowed_agents=["atlas", "hub", "navigator", "scout", "mentor"],
)
async def search_code_graph(
    context=None,
    project_id: str = "",
    query: str = "",
    name_pattern: str = "",
    semantic_query: str = "",
    label: str = "",
    limit: int = 200,
    offset: int = 0,
    **kw,
):
    from graph_engine_runtime import index_pipeline as pipeline
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id", "code": "VALIDATION_ERROR"}
    status = await pipeline.get_status_out(context.db, pid)
    if status["status"] != "READY":
        return {
            "error": "项目尚未索引就绪",
            "code": "GRAPH_NOT_INDEXED",
            "status": status["status"],
            "hint": "先调用 trigger_code_index",
        }
    client = GraphEngineClient()
    try:
        return await client.search_graph(
            status["engine_project"],
            query=query or "",
            name_pattern=name_pattern or "",
            semantic_query=semantic_query or "",
            label=label or None,
            limit=limit or 200,
            offset=offset or 0,
        )
    except GraphEngineError as exc:
        return {"error": exc.message, "code": exc.code}


@tool(
    name="search_code",
    description="grep 增强搜索：命中归并到函数并按重要度排序。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "pattern": {"type": "string"},
            "limit": {"type": "integer", "default": 50},
        },
        "required": ["project_id", "pattern"],
    },
    allowed_agents=["atlas", "hub", "navigator", "scout", "mentor"],
)
async def search_code(
    context=None,
    project_id: str = "",
    pattern: str = "",
    limit: int = 50,
    **kw,
):
    from graph_engine_runtime import index_pipeline as pipeline
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id", "code": "VALIDATION_ERROR"}
    status = await pipeline.get_status_out(context.db, pid)
    if status["status"] != "READY":
        return {"error": "项目尚未索引就绪", "code": "GRAPH_NOT_INDEXED", "status": status["status"]}
    client = GraphEngineClient()
    try:
        return await client.search_code(
            status["engine_project"], pattern=pattern, limit=limit or 50
        )
    except GraphEngineError as exc:
        return {"error": exc.message, "code": exc.code}


@tool(
    name="trace_calls",
    description="追踪代码图谱路径（trace_path）：calls / data_flow / cross_service，含风险分级。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "symbol": {"type": "string"},
            "direction": {
                "type": "string",
                "enum": ["upstream", "downstream", "both"],
                "default": "both",
            },
            "depth": {"type": "integer", "default": 3},
            "kind": {
                "type": "string",
                "enum": ["calls", "data_flow", "cross_service"],
                "default": "calls",
            },
        },
        "required": ["project_id", "symbol"],
    },
    allowed_agents=["atlas", "hub", "navigator"],
)
async def trace_calls(
    context=None,
    project_id: str = "",
    symbol: str = "",
    direction: str = "both",
    depth: int = 3,
    kind: str = "calls",
    **kw,
):
    from graph_engine_runtime import index_pipeline as pipeline
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id", "code": "VALIDATION_ERROR"}
    status = await pipeline.get_status_out(context.db, pid)
    if status["status"] != "READY":
        return {"error": "项目尚未索引就绪", "code": "GRAPH_NOT_INDEXED", "status": status["status"]}
    client = GraphEngineClient()
    try:
        return await client.trace_path(
            status["engine_project"],
            symbol=symbol,
            direction=direction or "both",
            depth=depth or 3,
            kind=kind or "calls",
        )
    except GraphEngineError as exc:
        return {"error": exc.message, "code": exc.code}


@tool(
    name="query_graph",
    description="对代码图谱执行 Cypher 子集查询（硬上限 10 万行）。可查复杂度字段如 cyclomatic_complexity。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 1000},
        },
        "required": ["project_id", "query"],
    },
    allowed_agents=["atlas", "hub", "navigator"],
)
async def query_graph(
    context=None,
    project_id: str = "",
    query: str = "",
    limit: int = 1000,
    **kw,
):
    from graph_engine_runtime import index_pipeline as pipeline
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id", "code": "VALIDATION_ERROR"}
    status = await pipeline.get_status_out(context.db, pid)
    if status["status"] != "READY":
        return {"error": "项目尚未索引就绪", "code": "GRAPH_NOT_INDEXED", "status": status["status"]}
    client = GraphEngineClient()
    try:
        return await client.query_graph(
            status["engine_project"], query, limit=min(limit or 1000, 100_000)
        )
    except GraphEngineError as exc:
        return {"error": exc.message, "code": exc.code}


@tool(
    name="get_graph_schema",
    description="获取代码图谱 schema：节点标签与边类型计数。",
    parameters={
        "type": "object",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    allowed_agents=["atlas", "hub", "navigator", "scout"],
)
async def get_graph_schema_tool(context=None, project_id: str = "", **kw):
    from graph_engine_runtime import index_pipeline as pipeline
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id", "code": "VALIDATION_ERROR"}
    status = await pipeline.get_status_out(context.db, pid)
    if status["status"] != "READY":
        return {"error": "项目尚未索引就绪", "code": "GRAPH_NOT_INDEXED", "status": status["status"]}
    client = GraphEngineClient()
    try:
        return await client.get_graph_schema(status["engine_project"])
    except GraphEngineError as exc:
        return {"error": exc.message, "code": exc.code}


@tool(
    name="get_project_architecture",
    description="获取已索引项目的架构视图：packages/clusters/layers/hotspots/boundaries。",
    parameters={
        "type": "object",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    },
    allowed_agents=["atlas", "hub", "scout", "navigator"],
)
async def get_project_architecture(context=None, project_id: str = "", **kw):
    from graph_engine_runtime import index_pipeline as pipeline
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id", "code": "VALIDATION_ERROR"}
    status = await pipeline.get_status_out(context.db, pid)
    if status["status"] != "READY":
        return {"error": "项目尚未索引就绪", "code": "GRAPH_NOT_INDEXED", "status": status["status"]}
    client = GraphEngineClient()
    try:
        return await client.get_architecture(status["engine_project"])
    except GraphEngineError as exc:
        return {"error": exc.message, "code": exc.code}


@tool(
    name="get_code_snippet_from_graph",
    description="按 qualified_name 从代码图谱取符号源码片段（get_code_snippet）。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "qualified_name": {"type": "string"},
        },
        "required": ["project_id", "qualified_name"],
    },
    allowed_agents=["atlas", "hub", "navigator", "mentor"],
)
async def get_code_snippet_from_graph(
    context=None,
    project_id: str = "",
    qualified_name: str = "",
    **kw,
):
    from graph_engine_runtime import index_pipeline as pipeline
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError

    try:
        pid = UUID(project_id)
    except Exception:
        return {"error": "invalid project_id", "code": "VALIDATION_ERROR"}
    status = await pipeline.get_status_out(context.db, pid)
    if status["status"] != "READY":
        return {"error": "项目尚未索引就绪", "code": "GRAPH_NOT_INDEXED", "status": status["status"]}
    client = GraphEngineClient()
    try:
        return await client.get_code_snippet(status["engine_project"], qualified_name)
    except GraphEngineError as exc:
        return {"error": exc.message, "code": exc.code}


@tool(
    name="list_categories",
    description="列出用户的项目分类。",
    parameters={"type": "object", "properties": {}},
    allowed_agents=["curator", "hub", "navigator", "scout"],
)
async def list_categories(context=None, **kw):
    cats = await _ports(context).categories.list_visible()
    return {
        "categories": [
            {"id": str(c.id), "name": c.name, "is_preset": bool(c.is_preset)}
            for c in cats
        ]
    }


@tool(
    name="suggest_category",
    description=(
        "仅作分类澄清/候选展示，不落库。"
        "意图明确时请改用 set_project_category 直接写入。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "category_name": {"type": "string"},
            "reason": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["category_name"],
    },
    allowed_agents=["curator"],
)
async def suggest_category(
    context=None,
    project_id: str = "",
    category_name: str = "",
    reason: str = "",
    confidence: float = 0.7,
    **kw,
):
    return {
        "suggestion": {
            "project_id": project_id,
            "category_name": category_name,
            "reason": reason,
            "confidence": confidence,
            "status": "pending_user_confirm",
        }
    }


@tool(
    name="list_notes",
    description="列出用户笔记，可按项目过滤。",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
    },
    allowed_agents=["scribe", "mentor", "navigator", "hub"],
)
async def list_notes(context=None, project_id: str = "", limit: int = 10, **kw):
    lim = min(limit or 10, 30)
    pid: UUID | None = None
    if project_id:
        try:
            pid = UUID(project_id)
        except ValueError:
            return {"error": "无效 project_id"}
    rows = await _ports(context).notes.list_for_user(
        project_id=pid, limit=lim
    )
    return {
        "notes": [
            {
                "id": str(n.id),
                "project_id": str(n.project_id),
                "title": n.title,
                "preview": (n.content or "")[:200],
            }
            for n in rows
        ]
    }


@tool(
    name="draft_note_outline",
    description="生成笔记大纲草稿（不直接写入数据库）。",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "章节标题列表",
            },
            "compare_with": {
                "type": "string",
                "description": "可选，对比的已学项目名",
            },
        },
        "required": ["title", "sections"],
    },
    allowed_agents=["scribe"],
)
async def draft_note_outline(
    context=None,
    title: str = "",
    sections: list | None = None,
    compare_with: str = "",
    **kw,
):
    sections = sections or []
    md = [f"# {title}", ""]
    for i, s in enumerate(sections, 1):
        md.append(f"## {i}. {s}")
        md.append("")
        md.append("<!-- 在此填写内容 -->")
        md.append("")
    if compare_with:
        md.append(f"## 与 {compare_with} 的对比")
        md.append("")
    return {"title": title, "markdown": "\n".join(md), "mode": "draft"}


@tool(
    name="ask_user",
    description=(
        "向用户发起结构化反问或测验，暂停当前流程等待回答。"
        "items 为问题列表，每项含 id/prompt/type/options。"
        "type: single_choice | multi_choice | scale | text | quiz。"
        "澄清需求、确认仓库来源、摸底水平：用 single_choice（不是测验）。"
        "只有考察掌握度/出考题时才用 type=quiz。"
        "禁止只在正文里出题让用户手打题号和答案。"
        "quiz：options 为候选答案；选项可为对象并带 correct=true 供批改。"
        "重要：options 必须是非空字符串数组，每个元素是完整选项文案，"
        "如 ['Thought→Action→Observation','Action→Observation→Thought']；"
        "禁止传空、禁止把一句话拆成单字符数组。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": [
                                "single_choice",
                                "multi_choice",
                                "scale",
                                "text",
                                "quiz",
                            ],
                        },
                        "options": {
                            "type": "array",
                            "items": {
                                "anyOf": [
                                    {"type": "string", "minLength": 2},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "value": {"type": "string"},
                                            "label": {"type": "string"},
                                            "text": {"type": "string"},
                                            "correct": {"type": "boolean"},
                                        },
                                    },
                                ]
                            },
                            "minItems": 2,
                        },
                        "required": {"type": "boolean"},
                    },
                    "required": ["id", "prompt", "type"],
                },
            },
            "allow_skip": {"type": "boolean", "default": True},
        },
        "required": ["title", "items"],
    },
    allowed_agents=["mentor", "navigator", "hub", "curator", "scout", "scribe"],
)
async def ask_user(
    context=None,
    title: str = "",
    items: list | None = None,
    allow_skip: bool = True,
    **kw,
):
    """特殊工具：返回 __question__ 标记，由 ReAct 引擎拦截。"""
    # 运行时再洗一遍 options，避免上游把字符串拆成字符列表
    cleaned_items: list[dict] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        prompt = str(it.get("prompt") or it.get("text") or "").strip()
        # 缺题干：用 title 仅当 title 不像通用面板标题
        if not prompt:
            t = str(title or "").strip()
            if t and t not in ("请回答以下问题", "请选择"):
                prompt = t
            else:
                prompt = "请选择最符合你情况的一项："
            it = {**it, "prompt": prompt}
        opts = it.get("options")
        if isinstance(opts, str):
            # 留给 normalize 解析；此处至少不 list(str)
            pass
        elif isinstance(opts, list) and len(opts) >= 2 and all(
            isinstance(x, str) and len(x) <= 1 for x in opts
        ):
            # 损坏的字符数组 → 清空，交给 normalize 兜底
            it = {**it, "options": []}
        cleaned_items.append(it)
    return {
        "__question__": True,
        "title": title or "请回答以下问题",
        "items": cleaned_items,
        "allow_skip": allow_skip,
        "agent_id": getattr(context, "agent_id", "hub"),
    }


@tool(
    name="manage_session_projects",
    description=(
        "管理当前会话绑定的项目上下文（可多选）。"
        "action=add 追加、remove 移除、set 整体替换。"
        "用户提到具体项目或需要对照多个仓库时调用；"
        "先用 query_user_projects 拿到真实 project_id，勿臆造。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "set"],
            },
            "project_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["action", "project_ids"],
    },
    allowed_agents=["hub", "navigator", "mentor", "scout", "curator", "scribe", "atlas"],
)
async def manage_session_projects(
    context=None,
    action: str = "add",
    project_ids: list | None = None,
    **kw,
):
    ports = _ports(context)
    raw_ids = [str(x).strip() for x in (project_ids or []) if str(x).strip()]
    parsed: list[UUID] = []
    for s in raw_ids:
        try:
            parsed.append(UUID(s))
        except ValueError:
            return {"error": f"无效 project_id: {s}"}

    session = await ports.sessions.get_owned(context.session_id)
    if not session:
        return {"error": "会话不存在"}

    act = (action or "add").strip().lower()
    try:
        ids = await ports.sessions.mutate_projects(
            session, act, parsed
        )
        await ports.commit()
    except ValueError:
        return {"error": "无权操作其中部分项目"}

    return {
        "ok": True,
        "action": act,
        "project_ids": [str(i) for i in ids],
        "count": len(ids),
        "__session_projects__": True,
        "__action__": "session_projects",
        "summary": f"会话已绑定 {len(ids)} 个项目",
        "links": [{"label": "项目库", "href": "/projects"}],
        "resource": {
            "type": "session",
            "project_ids": [str(i) for i in ids],
            "count": len(ids),
        },
    }


@tool(
    name="propose_memory",
    description=(
        "向 Hub 提交记忆/画像更新提案（不会立即写入；需用户在侧栏确认）。"
        "kind: long_memory | profile_tech | preference。"
        "profile_tech 的 value 格式如 'Python:75' 或 JSON。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "confidence": {"type": "number"},
            "kind": {
                "type": "string",
                "enum": ["long_memory", "profile_tech", "preference"],
            },
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["value", "kind"],
    },
    allowed_agents=["scout", "mentor", "navigator", "curator", "scribe", "hub", "atlas"],
)
async def propose_memory(
    context=None,
    value: str = "",
    confidence: float = 0.7,
    kind: str = "long_memory",
    evidence: list | None = None,
    **kw,
):
    proposal = await context.memory.propose_memory(
                agent_id=context.agent_id,
        value=value,
        confidence=confidence,
        evidence=evidence or [],
        kind=kind,
        apply=False,
    )
    return {
        "accepted": False,
        "pending": True,
        "applied": False,
        "proposal": proposal,
        "message": "记忆提案已排队，需用户确认后才会写入画像",
        "__memory_proposal__": True,
        "__action__": "memory_proposed",
        "summary": "记忆提案已排队，需在侧栏确认后写入",
        "ok": True,
    }


@tool(
    name="get_learner_info",
    description=(
        "按需获取本机学习者信息。仅在回答需要称呼、语言、技术栈、兴趣等时调用；"
        "fields 只填当前必要字段，禁止一次请求全部字段。"
        "可用: preferred_name, spoken_languages, programming_languages, tech_stack, "
        "interests, occupation, experience_level, bio, learning_preferences, "
        "tech_proficiency, goals, history_summary。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需要返回的字段名列表",
                "minItems": 1,
            }
        },
        "required": ["fields"],
    },
    allowed_agents=["scout", "mentor", "navigator", "curator", "scribe", "hub", "atlas"],
    timeout_ms=5_000,
)
async def get_learner_info(fields: list[str] | None = None, context=None, **kw):
    from agent_core import services as _agent_svc

    requested = fields or []
    if isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, list) or not requested:
        return {
            "error": "fields 必填且至少一项",
            "available_fields": sorted(_agent_svc.profile().LEARNER_INFO_FIELDS),
        }
    # 限制单次请求字段数，避免「假装按需实则全拉」
    capped = [str(f).strip() for f in requested if str(f).strip()][:6]
    profile = await _agent_svc.profile().get_user_profile(context.db)
    return _agent_svc.profile().select_learner_info(profile, capped)


@tool(
    name="get_learning_stats",
    description="获取用户学习统计：项目数、进度分布、笔记数等。",
    parameters={"type": "object", "properties": {}},
    allowed_agents=["navigator", "hub", "mentor", "atlas"],
)
async def get_learning_stats(context=None, **kw):
    ports = _ports(context)
    projects = await ports.projects.list_for_user(limit=10_000)
    note_count = await ports.notes.count_for_user()
    progress_dist: dict[str, int] = {}
    lang_dist: dict[str, int] = {}
    for p in projects:
        progress_dist[p.progress] = progress_dist.get(p.progress, 0) + 1
        if p.language:
            lang_dist[p.language] = lang_dist.get(p.language, 0) + 1
    return {
        "project_count": len(projects),
        "note_count": note_count,
        "progress_distribution": progress_dist,
        "language_distribution": lang_dist,
    }


@tool(
    name="dispatch_agent",
    description=(
        "Hub 专用：将子任务派发给专业 Agent。"
        "target_agent: scout|mentor|navigator|curator|scribe|atlas。"
        "task 必须结构化，包含："
        "1) 用户目标 2) 已知约束（反问答案/技术栈/水平）"
        "3) 禁止事项 4) 期望产出形态（路径表/验收点/下一步选项）。"
        "学习类优先只派 mentor；需要独立路线图再加 navigator；默认一次≤2。"
        "单专家：专家直出交舞台；多专家：Hub 汇总（专家作 Subagent，不单独出泡）。"
        "返回子任务描述，由 Hub 编排层实际执行。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "target_agent": {
                "type": "string",
                "enum": [
                    "scout",
                    "mentor",
                    "navigator",
                    "curator",
                    "scribe",
                    "atlas",
                ],
            },
            "task": {
                "type": "string",
                "description": (
                    "结构化任务说明：目标 / 约束 / 禁止 / 期望产出"
                ),
            },
            "reason": {"type": "string"},
        },
        "required": ["target_agent", "task"],
    },
    allowed_agents=["hub"],
)
async def dispatch_agent(
    context=None,
    target_agent: str = "",
    task: str = "",
    reason: str = "",
    **kw,
):
    from agent_core.agents.registry import get_registry

    # 运行时以注册表为准（工具 schema 的 enum 是静态白名单，加 Agent 后可能滞后）
    if not get_registry().has(target_agent):
        logger.warning("dispatch_agent to unregistered target: %s", target_agent)
        return {
            "error": f"目标 Agent 未注册: {target_agent}",
            "registered": sorted(d.id for d in get_registry().list_all()),
        }
    # task 来自 LLM 生成的 tool_call arguments：无长度限制会污染专家上下文，
    # 且超长/异常的模型输出可能放大 prompt 注入；入口处统一截断并记录。
    MAX_TASK_LEN = 4000
    if len(task or "") > MAX_TASK_LEN:
        logger.warning(
            "dispatch task truncated: target=%s len=%d -> %d",
            target_agent,
            len(task or ""),
            MAX_TASK_LEN,
        )
        task = (task or "")[:MAX_TASK_LEN]
    reason = (reason or "")[:500]
    return {
        "__dispatch__": True,
        "target_agent": target_agent,
        "task": task,
        "reason": reason or f"Hub 调度 {target_agent}",
    }


@tool(
    name="select_import_repos",
    description=(
        "导入场景专用：在左侧列表中勾选/取消勾选仓库（不真正导入）。"
        "repo_keys 形如 owner/repo。"
        "用户已明确要求导入时，请改用 import_github_repos 真正写入项目库。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "repo_keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "owner/repo 列表",
            },
            "action": {
                "type": "string",
                "enum": ["set", "add", "remove"],
                "default": "set",
            },
            "reason": {"type": "string", "description": "勾选理由，会展示给用户"},
        },
        "required": ["repo_keys"],
    },
    allowed_agents=["curator", "scout", "hub", "navigator"],
)
async def select_import_repos(
    context=None,
    repo_keys: list | None = None,
    action: str = "set",
    reason: str = "",
    **kw,
):
    keys = [str(k).strip() for k in (repo_keys or []) if str(k).strip()]
    # 与上下文 available 求交
    available = []
    if context and isinstance(getattr(context, "extra", None), dict):
        available = list(context.extra.get("available_repo_keys") or [])
    if available:
        avail_set = set(available)
        keys = [k for k in keys if k in avail_set]
    return {
        "__select_repos__": True,
        "__action__": "repos_selected",
        "ok": True,
        "repo_keys": keys,
        "action": action if action in ("set", "add", "remove") else "set",
        "reason": reason or "根据你的需求已在左侧勾选推荐仓库",
        "count": len(keys),
        "summary": f"已勾选 {len(keys)} 个仓库（尚未导入）",
        "links": [{"label": "打开项目库", "href": "/projects"}],
    }


# ---------------------------------------------------------------------------
# 真实写库工具（笔记 / 分类 / 标签 / 进度 / 导入）
# ---------------------------------------------------------------------------


def _action_result(
    action: str,
    *,
    summary: str,
    resource: dict[str, Any] | None = None,
    links: list[dict[str, str]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "__action__": action,
        "ok": True,
        "summary": summary,
        "links": links or [],
    }
    if resource is not None:
        out["resource"] = resource
    out.update(extra)
    return out


async def _get_owned_project_or_error(context, project_id: str):
    try:
        pid = UUID(str(project_id).strip())
    except ValueError:
        return None, {"error": "无效 project_id"}
    project = await _ports(context).projects.get_owned(pid)
    if not project:
        return None, {"error": "项目不存在或无权访问"}
    return project, None


@tool(
    name="create_note",
    description=(
        "在系统中真正创建并保存一篇笔记（写入数据库，用户可在笔记页反复查看）。"
        "用户要求生成/保存笔记、对话总结、多项目对比笔记时必须调用本工具，"
        "不要只输出正文而不落库。对比笔记：挂到主 project_id，"
        "compare_project_ids 写入结果元数据，对比内容写在 content 里。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "主项目 UUID"},
            "title": {"type": "string"},
            "content": {"type": "string", "description": "Markdown 正文"},
            "compare_project_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选，对比的其他项目 UUID",
            },
        },
        "required": ["project_id", "title", "content"],
    },
    allowed_agents=["scribe"],
    required_permission="allow_note_write",
)
async def create_note_tool(
    context=None,
    project_id: str = "",
    title: str = "",
    content: str = "",
    compare_project_ids: list | None = None,
    **kw,
):
    ports = _ports(context)
    project, err = await _get_owned_project_or_error(context, project_id)
    if err:
        return err
    title_s = (title or "").strip()
    if not title_s:
        return {"error": "标题不能为空"}
    body = content if content is not None else ""
    if len(body) > 100_000:
        return {"error": "正文过长"}

    compare_ids: list[str] = []
    for raw in compare_project_ids or []:
        s = str(raw).strip()
        if not s:
            continue
        try:
            cid = UUID(s)
        except ValueError:
            return {"error": f"无效 compare_project_id: {s}"}
        other = await ports.projects.get_owned(cid)
        if not other:
            return {"error": f"对比项目不存在或无权访问: {s}"}
        compare_ids.append(str(cid))

    note = await ports.notes.create(
        project_id=project.id,
        title=title_s[:256],
        content=body,
    )
    await ports.commit()

    href = f"/notes?note={note.id}&project={project.id}"
    return _action_result(
        "note_created",
        summary=f"已创建笔记《{note.title}》",
        resource={
            "type": "note",
            "id": str(note.id),
            "title": note.title,
            "project_id": str(project.id),
            "project_name": project.name,
            "compare_project_ids": compare_ids,
        },
        links=[
            {"label": "打开笔记", "href": href},
            {"label": "项目详情", "href": f"/projects/{project.id}"},
        ],
    )


@tool(
    name="update_note",
    description="更新已有笔记的标题和/或正文（真实写入数据库）。",
    parameters={
        "type": "object",
        "properties": {
            "note_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["note_id"],
    },
    allowed_agents=["scribe"],
    required_permission="allow_note_write",
)
async def update_note_tool(
    context=None,
    note_id: str = "",
    title: str | None = None,
    content: str | None = None,
    **kw,
):
    try:
        nid = UUID(str(note_id).strip())
    except ValueError:
        return {"error": "无效 note_id"}
    ports = _ports(context)
    fields: dict[str, Any] = {}
    if title is not None:
        t = str(title).strip()
        if not t:
            return {"error": "标题不能为空"}
        fields["title"] = t[:256]
    if content is not None:
        if len(content) > 100_000:
            return {"error": "正文过长"}
        fields["content"] = content
    if fields:
        from datetime import datetime

        fields["updated_at"] = datetime.utcnow()
    note = await ports.notes.update(nid, **fields)
    if not note:
        return {"error": "笔记不存在或无权访问"}
    await ports.commit()
    href = f"/notes?note={note.id}&project={note.project_id}"
    return _action_result(
        "note_updated",
        summary=f"已更新笔记《{note.title}》",
        resource={
            "type": "note",
            "id": str(note.id),
            "title": note.title,
            "project_id": str(note.project_id),
        },
        links=[{"label": "打开笔记", "href": href}],
    )


@tool(
    name="ensure_category",
    description="确保分类存在：按名称查找预设或用户分类，不存在则创建用户分类。",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "icon": {"type": "string"},
            "color": {"type": "string"},
        },
        "required": ["name"],
    },
    allowed_agents=["curator"],
    required_permission="allow_project_write",
)
async def ensure_category(
    context=None,
    name: str = "",
    icon: str = "",
    color: str = "",
    **kw,
):
    name_s = (name or "").strip()
    if not name_s:
        return {"error": "分类名称不能为空"}
    ports = _ports(context)
    cat, created = await ports.categories.ensure(
                name_s,
        icon=(icon or None) or None,
        color=(color or None) or None,
    )
    if created:
        await ports.commit()
    return _action_result(
        "category_ensured",
        summary=("已创建分类" if created else "分类已存在") + f"「{cat.name}」",
        resource={
            "type": "category",
            "id": str(cat.id),
            "name": cat.name,
            "created": created,
        },
        links=[{"label": "项目库", "href": "/projects"}],
    )


@tool(
    name="set_project_category",
    description=(
        "为项目设置分类并立即写入数据库。"
        "可传 category_id 或 category_name（名称不存在时会自动创建）。"
        "意图明确时直接调用，不要只 suggest。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "category_id": {"type": "string"},
            "category_name": {"type": "string"},
        },
        "required": ["project_id"],
    },
    allowed_agents=["curator"],
    required_permission="allow_project_write",
)
async def set_project_category(
    context=None,
    project_id: str = "",
    category_id: str = "",
    category_name: str = "",
    **kw,
):
    ports = _ports(context)
    project, err = await _get_owned_project_or_error(context, project_id)
    if err:
        return err
    cat = None
    if category_id:
        try:
            cid = UUID(str(category_id).strip())
        except ValueError:
            return {"error": "无效 category_id"}
        cat = await ports.categories.get_visible(cid)
        if not cat:
            return {"error": "分类不存在或无权使用"}
    elif category_name:
        cat, _created = await ports.categories.ensure(category_name.strip())
    else:
        return {"error": "需提供 category_id 或 category_name"}

    await ports.projects.update_fields(project, category_id=cat.id)
    await ports.commit()
    return _action_result(
        "category_applied",
        summary=f"已将「{project.name}」归入分类「{cat.name}」",
        resource={
            "type": "project",
            "id": str(project.id),
            "name": project.name,
            "category_id": str(cat.id),
            "category_name": cat.name,
        },
        links=[{"label": "打开项目", "href": f"/projects/{project.id}"}],
    )


@tool(
    name="list_tags",
    description="列出当前用户的全部标签。",
    parameters={"type": "object", "properties": {}},
    allowed_agents=["curator", "hub", "navigator", "scribe"],
)
async def list_tags(context=None, **kw):
    tags = await _ports(context).tags.list_with_counts()
    return {
        "tags": [{"id": str(t.id), "name": t.name, "count": t.count} for t in tags],
        "count": len(tags),
    }


@tool(
    name="ensure_tags",
    description="按名称确保标签存在，不存在则创建；返回标签 id 列表。",
    parameters={
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["names"],
    },
    allowed_agents=["curator"],
    required_permission="allow_project_write",
)
async def ensure_tags(context=None, names: list | None = None, **kw):
    ports = _ports(context)
    wanted = [str(n).strip() for n in (names or []) if str(n).strip()]
    if not wanted:
        return {"error": "names 不能为空"}
    existing = await ports.tags.list_for_user()
    before = {t.name for t in existing}
    tags = await ports.tags.ensure_many(wanted)
    await ports.commit()
    created = [t.name for t in tags if t.name not in before]
    out = [{"id": str(t.id), "name": t.name} for t in tags]
    return _action_result(
        "tags_ensured",
        summary=f"已准备 {len(out)} 个标签" + (f"（新建 {len(created)}）" if created else ""),
        resource={"type": "tags", "tags": out, "created_names": created},
        links=[{"label": "项目库", "href": "/projects"}],
    )


@tool(
    name="set_project_tags",
    description=(
        "为项目设置标签并写入数据库。"
        "可传 tag_ids，或传 tag_names（自动 ensure）。"
        "mode=replace 替换全部；mode=add 追加。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "tag_ids": {"type": "array", "items": {"type": "string"}},
            "tag_names": {"type": "array", "items": {"type": "string"}},
            "mode": {"type": "string", "enum": ["replace", "add"], "default": "replace"},
        },
        "required": ["project_id"],
    },
    allowed_agents=["curator"],
    required_permission="allow_project_write",
)
async def set_project_tags_tool(
    context=None,
    project_id: str = "",
    tag_ids: list | None = None,
    tag_names: list | None = None,
    mode: str = "replace",
    **kw,
):
    ports = _ports(context)
    project, err = await _get_owned_project_or_error(context, project_id)
    if err:
        return err
    resolved: list[UUID] = []
    from_ids: list[UUID] = []

    for raw in tag_ids or []:
        try:
            from_ids.append(UUID(str(raw).strip()))
        except ValueError:
            return {"error": f"无效 tag_id: {raw}"}

    if from_ids:
        valid = await ports.tags.validate_owned_ids(from_ids)
        valid_set = set(valid)
        invalid = [str(tid) for tid in from_ids if tid not in valid_set]
        if invalid:
            return {
                "error": f"无效或不属于你的 tag_id（已中止，未改动标签）: {', '.join(invalid)}"
            }
        resolved.extend(from_ids)

    names = [str(n).strip() for n in (tag_names or []) if str(n).strip()]
    if names:
        for tag in await ports.tags.ensure_many(names):
            if tag.id not in resolved:
                resolved.append(tag.id)

    act = (mode or "replace").strip().lower()
    if act == "add":
        current = await ports.tags.get_project_tag_ids(project.id)
        for tid in current:
            if tid not in resolved:
                resolved.append(tid)

    # set_on_project 内部会 commit
    result = await ports.tags.set_on_project(project.id, resolved)
    if result is None:
        return {"error": "设置标签失败"}

    tag_rows = []
    if result.tag_ids:
        by_id = {t.id: t for t in await ports.tags.list_for_user()}
        tag_rows = [
            {"id": str(tid), "name": by_id[tid].name}
            for tid in result.tag_ids
            if tid in by_id
        ]

    names_joined = "、".join(t["name"] for t in tag_rows) or "（清空）"
    return _action_result(
        "tags_applied",
        summary=f"已为「{project.name}」设置标签：{names_joined}",
        resource={
            "type": "project",
            "id": str(project.id),
            "name": project.name,
            "tags": tag_rows,
            "mode": act,
        },
        links=[{"label": "打开项目", "href": f"/projects/{project.id}"}],
    )


@tool(
    name="update_project_progress",
    description=(
        "更新项目学习进度并写入数据库。"
        "progress: none | learning | learned | mastered。"
        "用户说已掌握/学完/开始学时调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "progress": {
                "type": "string",
                "enum": ["none", "learning", "learned", "mastered"],
            },
        },
        "required": ["project_id", "progress"],
    },
    allowed_agents=["curator", "navigator", "mentor"],
    required_permission="allow_project_write",
)
async def update_project_progress(
    context=None,
    project_id: str = "",
    progress: str = "",
    **kw,
):
    ports = _ports(context)
    project, err = await _get_owned_project_or_error(context, project_id)
    if err:
        return err
    allowed = {"none", "learning", "learned", "mastered"}
    prog = (progress or "").strip().lower()
    if prog not in allowed:
        return {"error": f"无效 progress，可选: {', '.join(sorted(allowed))}"}
    prev = project.progress
    await ports.projects.update_fields(project, progress=prog)
    await ports.commit()
    labels = {
        "none": "未开始",
        "learning": "学习中",
        "learned": "已学会",
        "mastered": "已掌握",
    }
    return _action_result(
        "progress_updated",
        summary=f"已将「{project.name}」进度改为「{labels.get(prog, prog)}」",
        resource={
            "type": "project",
            "id": str(project.id),
            "name": project.name,
            "progress": prog,
            "previous_progress": prev,
        },
        links=[{"label": "打开项目", "href": f"/projects/{project.id}"}],
    )


@tool(
    name="import_github_repos",
    description=(
        "真正将 GitHub 仓库导入用户项目库（写入数据库）。"
        "repos 每项为 owner/repo 或 {owner,repo,url}。"
        "用户明确要求导入时调用；仅勾选预览请用 select_import_repos。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "repos": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {"type": "string"},
                        {
                            "type": "object",
                            "properties": {
                                "owner": {"type": "string"},
                                "repo": {"type": "string"},
                                "url": {"type": "string"},
                            },
                        },
                    ]
                },
            },
        },
        "required": ["repos"],
    },
    allowed_agents=["curator"],
    required_permission="allow_project_write",
    timeout_ms=120_000,
)
async def import_github_repos(
    context=None,
    repos: list | None = None,
    **kw,
):
    from py_shared.schemas.project import ImportRepoItem

    ports = _ports(context)
    items: list[ImportRepoItem] = []
    for raw in repos or []:
        owner = repo = url = ""
        if isinstance(raw, str):
            parts = raw.strip().split("/")
            if len(parts) == 2:
                owner, repo = parts[0], parts[1]
        elif isinstance(raw, dict):
            owner = str(raw.get("owner") or "").strip()
            repo = str(raw.get("repo") or "").strip()
            url = str(raw.get("url") or "").strip()
            if (not owner or not repo) and raw.get("full_name"):
                fn = str(raw["full_name"]).strip().split("/")
                if len(fn) == 2:
                    owner, repo = fn[0], fn[1]
        so, sr = _safe_github_name(owner), _safe_github_name(repo)
        if not so or not sr:
            return {"error": f"无效仓库标识: {raw}"}
        if not url:
            url = f"https://github.com/{so}/{sr}"
        try:
            items.append(ImportRepoItem(owner=so, repo=sr, url=url))
        except Exception as e:
            return {"error": f"无效导入项 {so}/{sr}: {e}"}

    if not items:
        return {"error": "repos 不能为空"}

    # import_repos 内部会 commit
    result = await ports.projects.import_repos(items)
    return _action_result(
        "repos_imported",
        summary=result.summary,
        resource={
            "type": "import",
            "succeeded": result.succeeded,
            "failed": result.failed,
            "errors": result.errors,
            "requested": [f"{i.owner}/{i.repo}" for i in items],
        },
        links=[{"label": "查看项目库", "href": "/projects"}],
        succeeded=result.succeeded,
        failed=result.failed,
    )


# §4.2.6: 模块级 @tool 装饰器是隐式副作用（import-time）。
# ensure_tools_loaded() 在外部多次调用应是幂等的；本函数仅为 API 兼容性保留。
_ENSURE_LOCK = threading.RLock()
_ENSURE_CALLED = False

def ensure_tools_loaded() -> None:
    """导入本模块以注册全部工具。

    §4.2.6: 幂等 + 线程安全；当前实现为 no-op（注册已在 import 时完成），
    保留函数签名以兼容外部调用方。
    """
    global _ENSURE_CALLED
    with _ENSURE_LOCK:
        _ENSURE_CALLED = True
    return None
