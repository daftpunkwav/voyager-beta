"""
图谱业务逻辑 —— 多信号 pairwise / foundation / hubness / cluster

无 LLM（或失败）时：角色/问题域/技术栈/作者 > 粗分类/语言。
启发式先落地；节点可预留 foundation_score / cluster_id 供后续 LLM 覆盖。
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from api_backend.models.project import Project, Tag, project_tags
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# 可调权重（角色/问题/栈/作者为主；语言与粗分类刻意降权防过拟合）
# ---------------------------------------------------------------------------
WEIGHTS = {
    "tfidf": 0.16,
    "problem": 0.14,
    "role": 0.16,
    "role_family": 0.08,
    "stack": 0.12,
    "author": 0.10,
    "tags": 0.08,
    "name": 0.06,
    "category": 0.05,
    "language": 0.04,
    "role_complement": 0.07,
    "stars_proximity": 0.03,
    "sparse_penalty_floor": 0.50,
    # 仅有语言/分类、几乎无结构信号时的衰减
    "shallow_signal_cap": 0.38,
}

FOUNDATION_W = {
    "lexicon": 0.55,
    "stars": 0.20,
    "centrality": 0.25,
}

HUBNESS_W = {
    "weighted_degree": 0.55,
    "avg_edge": 0.20,
    "neighbor_ratio": 0.25,
}

CLUSTER_MERGE_MIN_SIM = 0.35
CLUSTER_MAX_MERGE_RATIO = 0.92


def _target_cluster_count(n: int) -> int:
    """个人库常见百级项目：目标 6–10 个领域球，避免树状分层过多。"""
    if n <= 12:
        return max(1, n)
    if n <= 40:
        return max(3, min(6, n // 6))
    if n <= 100:
        return max(5, min(8, n // 14))
    return max(6, min(10, int(round(math.sqrt(n) * 0.65))))


def _adaptive_merge_threshold(n: int) -> float:
    """节点越多，合并阈值越低（只影响社区，不改 pairwise 分数）。"""
    if n >= 180:
        return 0.16
    if n >= 100:
        return 0.20
    if n >= 50:
        return 0.26
    return CLUSTER_MERGE_MIN_SIM

_TOKEN_RE = re.compile(r"[A-Za-z0-9_+#.-]{2,}|[\u4e00-\u9fff]{1,}")
_HOST_OWNER_RE = re.compile(
    r"(?:github\.com|gitee\.com|gitlab\.com|bitbucket\.org)[/:]([^/\s]+)/",
    re.I,
)

# 基础/应用词表（foundation_score）
FOUNDATION_LEXICON = frozenset(
    {
        "engine",
        "framework",
        "runtime",
        "database",
        "db",
        "kernel",
        "sdk",
        "protocol",
        "compiler",
        "vm",
        "interpreter",
        "stdlib",
        "infra",
        "infrastructure",
        "platform",
        "foundation",
        "core",
        "langchain",
        "langgraph",
        "mcp",
        "godot",
        "unity",
        "unreal",
        "cocos",
        "react",
        "vue",
        "angular",
        "fastapi",
        "flask",
        "django",
        "express",
        "nestjs",
        "spring",
        "springboot",
        "postgres",
        "postgresql",
        "mysql",
        "sqlite",
        "redis",
        "kubernetes",
        "k8s",
        "docker",
        "llvm",
        "wasm",
    }
)

APPLICATION_LEXICON = frozenset(
    {
        "game",
        "demo",
        "ecommerce",
        "e-commerce",
        "shop",
        "skill",
        "skills",
        "bot",
        "starter",
        "template",
        "boilerplate",
        "example",
        "examples",
        "tutorial",
        "playground",
        "clone",
        "app",
        "application",
        "cms",
        "blog",
        "chat",
        "agent-app",
        "wrapper",
        "plugin",
        "theme",
        "dashboard",
        "admin",
        "saas",
    }
)

# 项目角色：游戏 / agent / 工具 / skill / mcp / 框架(细分) / 组件库 / API…
ROLE_KEYWORDS: dict[str, frozenset[str]] = {
    "game": frozenset(
        {"game", "gamedev", "platformer", "roguelike", "fps", "rpg", "indie-game", "游戏"}
    ),
    "game_engine": frozenset(
        {"godot", "unity", "unreal", "cocos", "game-engine", "gameengine", "引擎"}
    ),
    "agent": frozenset(
        {"agent", "agents", "autogpt", "open-interpreter", "autonomous-agent", "智能体"}
    ),
    "agent_framework": frozenset(
        {
            "langchain",
            "langgraph",
            "crewai",
            "autogen",
            "semantic-kernel",
            "agent-framework",
            "agentic-framework",
        }
    ),
    "mcp": frozenset(
        {"mcp", "mcp-server", "model-context-protocol", "mcp-client", "mcp服务器"}
    ),
    "skill": frozenset({"skill", "skills", "claude-skill", "agent-skill", "技能"}),
    "tool": frozenset(
        {"cli", "command-line", "devtools", "developer-tool", "utility", "工具", "toolkit"}
    ),
    "web_framework": frozenset(
        {
            "react",
            "vue",
            "angular",
            "nextjs",
            "next.js",
            "nuxt",
            "svelte",
            "fastapi",
            "flask",
            "django",
            "express",
            "nestjs",
            "spring",
            "springboot",
            "web-framework",
            "前端框架",
            "后端框架",
        }
    ),
    "component_lib": frozenset(
        {
            "component",
            "components",
            "ui-kit",
            "design-system",
            "component-library",
            "antd",
            "mui",
            "shadcn",
            "组件库",
        }
    ),
    "api": frozenset(
        {"api", "rest", "restful", "graphql", "openapi", "grpc", "sdk", "接口", "api-gateway"}
    ),
    "database": frozenset(
        {"database", "db", "postgres", "postgresql", "mysql", "sqlite", "redis", "mongodb", "数据库"}
    ),
    "devops": frozenset(
        {"devops", "ci", "cd", "kubernetes", "k8s", "docker", "terraform", "helm", "infra"}
    ),
    "frontend_app": frozenset(
        {"dashboard", "admin", "spa", "frontend-app", "webapp", "saas", "cms", "blog"}
    ),
}

# 角色族：同族可中等关联；跨族且无共享问题则冲突衰减
ROLE_FAMILY: dict[str, str] = {
    "game": "game",
    "game_engine": "game",
    "agent": "ai_agent",
    "agent_framework": "ai_agent",
    "mcp": "ai_agent",
    "skill": "ai_agent",
    "tool": "tooling",
    "web_framework": "web",
    "component_lib": "web",
    "frontend_app": "web",
    "api": "backend",
    "database": "data",
    "devops": "infra",
}

# 同族内「基础↔应用」互补对
ROLE_COMPLEMENT_PAIRS = frozenset(
    {
        frozenset({"game_engine", "game"}),
        frozenset({"agent_framework", "agent"}),
        frozenset({"agent_framework", "skill"}),
        frozenset({"mcp", "agent"}),
        frozenset({"mcp", "skill"}),
        frozenset({"web_framework", "frontend_app"}),
        frozenset({"web_framework", "component_lib"}),
        frozenset({"component_lib", "frontend_app"}),
        frozenset({"api", "frontend_app"}),
        frozenset({"database", "api"}),
        frozenset({"database", "web_framework"}),
    }
)

# 顶层应用/平台技术栈
STACK_KEYWORDS: dict[str, frozenset[str]] = {
    "react": frozenset({"react", "reactjs", "jsx", "nextjs", "next.js", "remix"}),
    "vue": frozenset({"vue", "vuejs", "nuxt", "vitepress"}),
    "angular": frozenset({"angular", "rxjs"}),
    "svelte": frozenset({"svelte", "sveltekit"}),
    "node": frozenset({"nodejs", "node.js", "express", "nestjs", "npm", "pnpm"}),
    "python_web": frozenset({"fastapi", "flask", "django", "uvicorn", "starlette"}),
    "jvm": frozenset({"java", "kotlin", "spring", "springboot", "jvm"}),
    "dotnet": frozenset({"dotnet", ".net", "csharp", "aspnet"}),
    "llm_orch": frozenset(
        {"langchain", "langgraph", "llamaindex", "crewai", "autogen", "semantic-kernel"}
    ),
    "mcp_ecosystem": frozenset({"mcp", "mcp-server", "model-context-protocol"}),
    "godot": frozenset({"godot", "gdscript"}),
    "unity": frozenset({"unity", "csharp", "unity3d"}),
    "unreal": frozenset({"unreal", "ue5", "unrealengine"}),
    "threejs": frozenset({"three", "threejs", "webgl", "babylon"}),
    "data_store": frozenset({"postgres", "postgresql", "mysql", "sqlite", "redis", "mongodb"}),
    "k8s": frozenset({"kubernetes", "k8s", "helm", "istio"}),
    "electron": frozenset({"electron", "tauri", "desktop-app"}),
}

# 问题域：是否在解决同一类问题
PROBLEM_KEYWORDS: dict[str, frozenset[str]] = {
    "rag": frozenset({"rag", "retrieval", "embedding", "vector", "vectorstore", "知识库"}),
    "chat": frozenset({"chat", "chatbot", "conversation", "对话", "messenger"}),
    "auth": frozenset({"auth", "oauth", "oidc", "sso", "login", "identity", "认证"}),
    "codegen": frozenset({"codegen", "code-gen", "copilot", "codex", "code-assistant", "编程助手"}),
    "viz": frozenset({"visualization", "viz", "chart", "graph-viz", "d3", "echarts", "可视化"}),
    "ecommerce": frozenset({"ecommerce", "e-commerce", "shop", "cart", "checkout", "电商"}),
    "search": frozenset({"search", "elasticsearch", "全文检索", "全文搜索"}),
    "observability": frozenset({"observability", "tracing", "metrics", "logging", "otel", "监控"}),
    "ci_cd": frozenset({"ci", "cd", "pipeline", "github-actions", "gitlab-ci", "持续集成"}),
    "editor": frozenset({"editor", "ide", "lsp", "monaco", "codemirror", "编辑器"}),
    "prompt": frozenset({"prompt", "prompt-engineering", "system-prompt", "提示词"}),
    "multi_agent": frozenset({"multi-agent", "orchestration", "workflow-agent", "多智能体"}),
    "ui_system": frozenset({"design-system", "ui-kit", "accessibility", "a11y", "主题"}),
    "gamedev": frozenset({"gamedev", "gameplay", "physics", "sprite", "tilemap", "游戏开发"}),
}

FOUNDATION_ROLES = frozenset(
    {"game_engine", "agent_framework", "web_framework", "database", "devops", "api", "mcp"}
)
APPLICATION_ROLES = frozenset(
    {"game", "agent", "skill", "frontend_app", "tool"}
)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _tf(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    c = Counter(tokens)
    n = len(tokens)
    return {k: v / n for k, v in c.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _doc_tokens(p: Project) -> list[str]:
    # 故意不含 language：语言走独立弱信号，避免 TF-IDF 过拟合同语言
    text = " ".join(
        filter(
            None,
            [
                p.name or "",
                p.description or "",
                p.note or "",
            ],
        )
    )
    return _tokenize(text)


def _doc_vector(p: Project) -> dict[str, float]:
    """兼容旧测试：纯 TF 向量。"""
    return _tf(_doc_tokens(p))


def _build_idf(docs: list[list[str]]) -> dict[str, float]:
    n = len(docs)
    if n == 0:
        return {}
    df: Counter[str] = Counter()
    for toks in docs:
        df.update(set(toks))
    return {t: math.log((n + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}


def _tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}
    tf = _tf(tokens)
    return {k: v * idf.get(k, 1.0) for k, v in tf.items()}


def _lexicon_hits(tokens: list[str], lexicon: frozenset[str]) -> set[str]:
    hits: set[str] = set()
    joined = " ".join(tokens)
    for w in lexicon:
        if w in tokens or (len(w) >= 3 and w in joined):
            hits.add(w)
    return hits


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _stars_proximity(sa: int, sb: int) -> float:
    cap = 12.0
    diff = abs(math.log1p(max(0, sa)) - math.log1p(max(0, sb)))
    return max(0.0, 1.0 - diff / cap)


def _sparse_multiplier(
    tokens_a: list[str],
    tokens_b: list[str],
    *,
    text_sim: float,
) -> float:
    """描述过稀时衰减；高文本相似时不惩罚。"""
    if text_sim >= 0.75:
        return 1.0
    n = min(len(tokens_a), len(tokens_b))
    if n >= 8:
        return 1.0
    if n == 0:
        return WEIGHTS["sparse_penalty_floor"]
    t = n / 8.0
    floor = WEIGHTS["sparse_penalty_floor"]
    return floor + (1.0 - floor) * t


def _project_tags_map(
    tag_rows: list[tuple[UUID, str]],
) -> dict[UUID, set[str]]:
    out: dict[UUID, set[str]] = defaultdict(set)
    for pid, name in tag_rows:
        if name:
            out[pid].add(name.lower())
    return out


def _repo_owner(url: str | None) -> str | None:
    if not url:
        return None
    m = _HOST_OWNER_RE.search(url)
    if not m:
        return None
    owner = m.group(1).lower()
    if owner in {"www", "http", "https"}:
        return None
    return owner


def _score_keyed_lexicon(
    tokens: list[str],
    blob: str,
    mapping: dict[str, frozenset[str]],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for key, kws in mapping.items():
        hits = 0.0
        for kw in kws:
            if kw in tokens:
                hits += 1.0
            elif len(kw) >= 3 and kw in blob:
                hits += 0.7
        if hits > 0:
            scores[key] = hits
    return scores


@dataclass
class ProjectProfile:
    tokens: list[str]
    roles: dict[str, float] = field(default_factory=dict)
    primary_role: str | None = None
    stacks: set[str] = field(default_factory=set)
    problems: set[str] = field(default_factory=set)
    owner: str | None = None
    tags: set[str] = field(default_factory=set)


def _build_profile(
    p: Project,
    *,
    tokens: list[str] | None = None,
    tags: set[str] | None = None,
) -> ProjectProfile:
    toks = tokens if tokens is not None else _doc_tokens(p)
    tag_set = {t.lower() for t in (tags or set()) if t}
    blob = " ".join(
        x
        for x in [
            (p.name or "").lower(),
            (p.description or "").lower(),
            (p.note or "").lower(),
            (p.language or "").lower(),
            " ".join(sorted(tag_set)),
        ]
        if x
    )
    role_scores = _score_keyed_lexicon(toks, blob, ROLE_KEYWORDS)
    # 标签名直接命中角色键
    for t in tag_set:
        for role, kws in ROLE_KEYWORDS.items():
            if t == role or t in kws:
                role_scores[role] = role_scores.get(role, 0.0) + 1.2

    primary = max(role_scores, key=lambda k: role_scores[k]) if role_scores else None
    stacks = set(_score_keyed_lexicon(toks, blob, STACK_KEYWORDS))
    problems = set(_score_keyed_lexicon(toks, blob, PROBLEM_KEYWORDS))
    return ProjectProfile(
        tokens=toks,
        roles=role_scores,
        primary_role=primary,
        stacks=stacks,
        problems=problems,
        owner=_repo_owner(p.url),
        tags=tag_set,
    )


def _role_overlap(pa: ProjectProfile, pb: ProjectProfile) -> tuple[float, float, bool]:
    """返回 (主角色一致分, 角色族分, 是否存在互补对)。"""
    same_primary = 0.0
    if pa.primary_role and pa.primary_role == pb.primary_role:
        same_primary = 1.0
    elif pa.roles and pb.roles:
        shared = set(pa.roles) & set(pb.roles)
        if shared:
            # 次级角色重叠：按归一化命中强度
            num = sum(min(pa.roles[r], pb.roles[r]) for r in shared)
            den = max(sum(pa.roles.values()), sum(pb.roles.values()), 1.0)
            same_primary = min(1.0, 0.55 + 0.45 * (num / den))

    family = 0.0
    fa = ROLE_FAMILY.get(pa.primary_role or "", "")
    fb = ROLE_FAMILY.get(pb.primary_role or "", "")
    if fa and fb and fa == fb and pa.primary_role != pb.primary_role:
        family = 0.85
    elif pa.roles and pb.roles:
        fams_a = {ROLE_FAMILY.get(r) for r in pa.roles if r in ROLE_FAMILY}
        fams_b = {ROLE_FAMILY.get(r) for r in pb.roles if r in ROLE_FAMILY}
        if fams_a & fams_b:
            family = max(family, 0.55)

    complement = False
    roles_a = set(pa.roles) | ({pa.primary_role} if pa.primary_role else set())
    roles_b = set(pb.roles) | ({pb.primary_role} if pb.primary_role else set())
    for ra in roles_a:
        for rb in roles_b:
            if frozenset({ra, rb}) in ROLE_COMPLEMENT_PAIRS:
                complement = True
                break
        if complement:
            break
    return same_primary, family, complement


def _roles_conflict(pa: ProjectProfile, pb: ProjectProfile) -> bool:
    """跨族且无共享问题/栈时视为冲突（抑制纯语言边）。"""
    if not pa.primary_role or not pb.primary_role:
        return False
    fa = ROLE_FAMILY.get(pa.primary_role)
    fb = ROLE_FAMILY.get(pb.primary_role)
    if not fa or not fb or fa == fb:
        return False
    if pa.problems & pb.problems:
        return False
    if pa.stacks & pb.stacks:
        return False
    return True


def _similarity_detailed(
    a: Project,
    b: Project,
    va: dict[str, float],
    vb: dict[str, float],
    *,
    tags_a: set[str] | None = None,
    tags_b: set[str] | None = None,
    tokens_a: list[str] | None = None,
    tokens_b: list[str] | None = None,
    profile_a: ProjectProfile | None = None,
    profile_b: ProjectProfile | None = None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    structural = 0.0  # 非语言/分类信号累计，用于防过拟合

    # 两侧几乎无文本时不因默认 URL/空壳拉边
    if not ((a.name or a.description or a.note) and (b.name or b.description or b.note)):
        return 0.0, []

    pa = profile_a or _build_profile(a, tokens=tokens_a, tags=tags_a)
    pb = profile_b or _build_profile(b, tokens=tokens_b, tags=tags_b)
    ta, tb = pa.tokens, pb.tokens

    text_sim = _cosine(va, vb)
    if text_sim > 0.05:
        w = WEIGHTS["tfidf"] * text_sim
        score += w
        structural += w
        if text_sim >= 0.2:
            reasons.append("tfidf")

    problem_j = _jaccard(pa.problems, pb.problems)
    if problem_j > 0:
        w = WEIGHTS["problem"] * problem_j
        score += w
        structural += w
        if problem_j >= 0.34:
            reasons.append("problem")

    role_same, role_family, complement = _role_overlap(pa, pb)
    if role_same > 0:
        w = WEIGHTS["role"] * role_same
        score += w
        structural += w
        if role_same >= 0.55:
            reasons.append("role")
    if role_family > 0 and role_same < 0.95:
        w = WEIGHTS["role_family"] * role_family
        score += w
        structural += w
        reasons.append("role_family")

    stack_j = _jaccard(pa.stacks, pb.stacks)
    if stack_j > 0:
        w = WEIGHTS["stack"] * stack_j
        score += w
        structural += w
        if stack_j >= 0.34:
            reasons.append("stack")

    if (
        pa.owner
        and pb.owner
        and pa.owner == pb.owner
        and (a.name or a.description)
        and (b.name or b.description)
    ):
        w = WEIGHTS["author"]
        score += w
        structural += w
        reasons.append("author")

    tag_j = _jaccard(pa.tags, pb.tags)
    if tag_j > 0:
        w = WEIGHTS["tags"] * tag_j
        score += w
        structural += w
        if tag_j >= 0.25:
            reasons.append("tags")

    name_a = set(_tokenize(a.name or ""))
    name_b = set(_tokenize(b.name or ""))
    name_j = _jaccard(name_a, name_b)
    if name_j > 0:
        w = WEIGHTS["name"] * name_j
        score += w
        structural += w
        if name_j >= 0.3:
            reasons.append("name")

    if complement and (problem_j > 0 or stack_j > 0 or role_family > 0):
        w = WEIGHTS["role_complement"] * min(1.0, 0.55 + 0.45 * max(problem_j, stack_j, role_family))
        score += w
        structural += w
        reasons.append("role_complement")

    shallow = 0.0
    if a.category_id and b.category_id and a.category_id == b.category_id:
        shallow += WEIGHTS["category"]
        reasons.append("category")
    if a.language and b.language and a.language == b.language:
        shallow += WEIGHTS["language"]
        reasons.append("language")
    score += shallow

    # 纯语言/分类边：大幅衰减（核心防过拟合）
    if shallow > 0 and structural < 0.06:
        score *= WEIGHTS["shallow_signal_cap"]
    elif _roles_conflict(pa, pb) and structural < 0.12:
        score *= 0.62

    has_content = bool(
        (a.name or a.description or a.note or a.language)
        and (b.name or b.description or b.note or b.language)
    )
    stars_p = _stars_proximity(a.stars or 0, b.stars or 0)
    if has_content and stars_p > 0.4 and score > 0 and structural > 0.04:
        score += WEIGHTS["stars_proximity"] * stars_p
        if stars_p >= 0.7:
            reasons.append("stars")

    if score > 0:
        score *= _sparse_multiplier(ta, tb, text_sim=text_sim)
    return min(score, 1.0), reasons


def _similarity(a: Project, b: Project) -> float:
    toks_a, toks_b = _doc_tokens(a), _doc_tokens(b)
    idf = _build_idf([toks_a, toks_b])
    sim, _ = _similarity_detailed(
        a,
        b,
        _tfidf(toks_a, idf),
        _tfidf(toks_b, idf),
        tokens_a=toks_a,
        tokens_b=toks_b,
    )
    return sim


def _lexicon_foundation_raw(tokens: list[str], primary_role: str | None = None) -> float:
    f = len(_lexicon_hits(tokens, FOUNDATION_LEXICON))
    a = len(_lexicon_hits(tokens, APPLICATION_LEXICON))
    if primary_role in FOUNDATION_ROLES:
        f += 2
    if primary_role in APPLICATION_ROLES:
        a += 2
    if f == 0 and a == 0:
        return 0.35
    raw = (f * 1.0 - a * 0.85) / max(1.0, f + a)
    return max(0.0, min(1.0, 0.5 + 0.5 * raw))


def _compute_foundation(
    p: Project,
    tokens: list[str],
    centrality: float,
    override: float | None = None,
    *,
    profile: ProjectProfile | None = None,
) -> float:
    if override is not None:
        return max(0.0, min(1.0, override))
    prof = profile or _build_profile(p, tokens=tokens)
    lex = _lexicon_foundation_raw(tokens, prof.primary_role)
    stars_n = min(1.0, math.log1p(p.stars or 0) / math.log1p(200_000))
    score = (
        FOUNDATION_W["lexicon"] * lex
        + FOUNDATION_W["stars"] * stars_n
        + FOUNDATION_W["centrality"] * centrality
    )
    return max(0.0, min(1.0, score))


def _compute_hubness(
    weighted_degree: float,
    avg_edge: float,
    neighbor_ratio: float,
) -> float:
    score = (
        HUBNESS_W["weighted_degree"] * weighted_degree
        + HUBNESS_W["avg_edge"] * avg_edge
        + HUBNESS_W["neighbor_ratio"] * neighbor_ratio
    )
    return max(0.0, min(1.0, score))


def _cluster_communities(
    node_ids: list[str],
    edges: list[dict],
) -> dict[str, str]:
    """自适应阈值并查集 + 向目标社区数粗化。"""
    parent = {nid: nid for nid in node_ids}
    n = len(node_ids)
    if n == 0:
        return {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb
        return True

    sorted_edges = sorted(edges, key=lambda e: e["similarity"], reverse=True)
    thr = _adaptive_merge_threshold(n)
    max_merge = max(1, int(n * CLUSTER_MAX_MERGE_RATIO))
    merges = 0
    for e in sorted_edges:
        if e["similarity"] < thr:
            break
        if merges >= max_merge:
            break
        if union(e["source"], e["target"]):
            merges += 1

    # 仍过多时：按跨社区边权把小社区并入强连接邻居，直到目标数
    target = _target_cluster_count(n)
    cross: dict[tuple[str, str], float] = defaultdict(float)
    for e in sorted_edges:
        ra, rb = find(e["source"]), find(e["target"])
        if ra == rb:
            continue
        a, b = (ra, rb) if ra < rb else (rb, ra)
        cross[(a, b)] += float(e["similarity"])

    def community_sizes() -> dict[str, int]:
        sizes: Counter[str] = Counter(find(nid) for nid in node_ids)
        return dict(sizes)

    sizes = community_sizes()
    while len(sizes) > target:
        # 选最小社区，并入与之跨边最强的社区
        small = min(sizes.items(), key=lambda kv: (kv[1], kv[0]))[0]
        best: tuple[str, float] | None = None
        for (a, b), w in cross.items():
            other = b if a == small else a if b == small else None
            if other is None or other not in sizes:
                continue
            if best is None or w > best[1]:
                best = (other, w)
        if best is None:
            # 无跨边：并入任意较大社区
            large = max(
                (kv for kv in sizes.items() if kv[0] != small),
                key=lambda kv: (kv[1], kv[0]),
                default=None,
            )
            if large is None:
                break
            union(small, large[0])
        else:
            union(small, best[0])
        # 刷新
        sizes = community_sizes()
        cross = defaultdict(float)
        for e in sorted_edges:
            ra, rb = find(e["source"]), find(e["target"])
            if ra == rb:
                continue
            a, b = (ra, rb) if ra < rb else (rb, ra)
            cross[(a, b)] += float(e["similarity"])

    return {nid: find(nid) for nid in node_ids}


async def _load_project_tags(
    db: AsyncSession, project_ids: list[UUID]
) -> dict[UUID, set[str]]:
    if not project_ids:
        return {}
    q = (
        select(project_tags.c.project_id, Tag.name)
        .join(Tag, Tag.id == project_tags.c.tag_id)
        .where(project_tags.c.project_id.in_(project_ids))
    )
    result = await db.execute(q)
    return _project_tags_map([(row[0], row[1]) for row in result.all()])


async def build_graph(
    db: AsyncSession,
    *,
    min_similarity: float = 0.3,
    max_edges: int = 200,
) -> dict:
    result = await db.execute(select(Project))
    projects = list(result.scalars().all())
    tag_map = await _load_project_tags(db, [p.id for p in projects])

    token_map = {p.id: _doc_tokens(p) for p in projects}
    idf = _build_idf(list(token_map.values()))
    vectors = {p.id: _tfidf(token_map[p.id], idf) for p in projects}
    profile_map = {
        p.id: _build_profile(p, tokens=token_map[p.id], tags=tag_map.get(p.id, set()))
        for p in projects
    }

    # 全量 pairwise（社区 / hubness 用），再按阈值截断返回边
    all_edges: list[dict] = []
    for i, a in enumerate(projects):
        for b in projects[i + 1 :]:
            sim, reasons = _similarity_detailed(
                a,
                b,
                vectors[a.id],
                vectors[b.id],
                tags_a=tag_map.get(a.id, set()),
                tags_b=tag_map.get(b.id, set()),
                tokens_a=token_map[a.id],
                tokens_b=token_map[b.id],
                profile_a=profile_map[a.id],
                profile_b=profile_map[b.id],
            )
            if sim >= min_similarity:
                all_edges.append(
                    {
                        "source": str(a.id),
                        "target": str(b.id),
                        "similarity": round(sim, 3),
                        "relation": reasons[0] if reasons else "similarity",
                        "reasons": reasons or ["similarity"],
                        "edge_type": "similarity",
                    }
                )

    all_edges.sort(key=lambda e: e["similarity"], reverse=True)

    # 加权度（全量过阈边）
    wdeg: dict[str, float] = defaultdict(float)
    neigh: dict[str, set[str]] = defaultdict(set)
    for e in all_edges:
        s, t, w = e["source"], e["target"], e["similarity"]
        wdeg[s] += w
        wdeg[t] += w
        neigh[s].add(t)
        neigh[t].add(s)

    max_wdeg = max(wdeg.values()) if wdeg else 1.0
    n_nodes = max(len(projects), 1)

    # 归一中心性 → foundation / hubness
    centrality = {str(p.id): (wdeg[str(p.id)] / max_wdeg if max_wdeg else 0.0) for p in projects}

    # 预留覆盖：ORM 若将来有 foundation_score_override / cluster_id_override 则读取
    foundations: dict[str, float] = {}
    for p in projects:
        pid = str(p.id)
        override = getattr(p, "foundation_score_override", None)
        foundations[pid] = round(
            _compute_foundation(
                p,
                token_map[p.id],
                centrality[pid],
                override,
                profile=profile_map[p.id],
            ),
            3,
        )

    hubness: dict[str, float] = {}
    for p in projects:
        pid = str(p.id)
        nbrs = neigh.get(pid, set())
        avg_e = (wdeg[pid] / len(nbrs)) if nbrs else 0.0
        hubness[pid] = round(
            _compute_hubness(
                centrality[pid],
                min(1.0, avg_e),
                len(nbrs) / n_nodes,
            ),
            3,
        )

    node_ids = [str(p.id) for p in projects]
    # 社区用全量边；若节点有 cluster_id_override 则优先
    communities = _cluster_communities(node_ids, all_edges)
    for p in projects:
        ov = getattr(p, "cluster_id_override", None)
        if ov:
            communities[str(p.id)] = str(ov)

    cluster_sizes: Counter[str] = Counter(communities.values())

    nodes = []
    for p in projects:
        pid = str(p.id)
        cid = communities.get(pid, pid)
        nodes.append(
            {
                "id": pid,
                "name": p.name,
                "language": p.language,
                "category_id": str(p.category_id) if p.category_id else None,
                "progress": p.progress,
                "stars": p.stars,
                "description": (p.description or "")[:160],
                "url": p.url,
                "foundation_score": foundations[pid],
                "hubness": hubness[pid],
                "cluster_id": cid,
                "cluster_size": cluster_sizes[cid],
            }
        )

    edges = all_edges[:max_edges]
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "avg_similarity": round(
                sum(e["similarity"] for e in edges) / max(len(edges), 1),
                3,
            )
            if edges
            else 0.0,
        },
    }


async def build_cross_edges(db: AsyncSession) -> list[dict]:
    """从已 READY 项目跑/读取跨仓边；引擎不可用时返回空列表（不影响 L0 相似度）。"""
    from graph_engine_runtime.client import GraphEngineClient, GraphEngineError
    from py_shared.models.graph_index import GraphIndexStatus

    result = await db.execute(
        select(GraphIndexStatus).where(GraphIndexStatus.status == "READY")
    )
    rows = list(result.scalars().all())
    if len(rows) < 2:
        return []

    engine_to_project = {
        r.engine_project: str(r.project_id) for r in rows if r.engine_project
    }
    names = list(engine_to_project.keys())
    client = GraphEngineClient()
    if not await client.health():
        return []

    first_path = next((r.local_path for r in rows if r.local_path), ".") or "."
    try:
        raw = await client.index_repository(
            first_path,
            mode="cross-repo-intelligence",
            target_projects=names,
        )
    except GraphEngineError:
        return []

    edges: list[dict] = []
    raw_edges = raw.get("edges") if isinstance(raw, dict) else None
    if not isinstance(raw_edges, list):
        try:
            raw_edges = await client.list_cross_edges()
        except Exception:
            raw_edges = []

    for row in raw_edges or []:
        if not isinstance(row, dict):
            continue
        src_e = str(row.get("source_engine") or "")
        dst_e = str(row.get("target_engine") or "")
        rel = str(row.get("type") or row.get("relation") or "CROSS_SHARED_SYMBOL")
        relation = "cross_shared"
        if "HTTP" in rel:
            relation = "cross_http"
        elif "ASYNC" in rel:
            relation = "cross_async"
        elif "CHANNEL" in rel:
            relation = "cross_channel"
        edges.append(
            {
                "source": engine_to_project.get(src_e, src_e),
                "target": engine_to_project.get(dst_e, dst_e),
                "source_engine": src_e,
                "target_engine": dst_e,
                "relation": relation,
                "weight": float(row.get("weight") or 1.0),
                "reasons": [
                    rel,
                    str(row.get("source_symbol") or ""),
                    str(row.get("target_symbol") or ""),
                ],
                "source_symbol": row.get("source_symbol"),
                "target_symbol": row.get("target_symbol"),
                "similarity": 1.0,
            }
        )
    return edges
