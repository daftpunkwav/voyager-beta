"""静态解析索引 —— 对照 codebase-memory-mcp 多遍流水线（结构/定义/文档 Section）。

目标节点类型对齐原生引擎：
Project / Branch / Folder / File / Module / Section / Function / Method /
Class / Interface / Type / Variable / Route / Decorator / EnvVar / Macro
"""
from __future__ import annotations

import ast
import fnmatch
import hashlib
import os
import re
from pathlib import Path
from typing import Iterable

from .store import Edge, GraphStore, Node, force_layout_3d

# Non-negatable safety core：与 C 引擎 discover.c is_safety_core_dir 对齐——
# 仓库提交的 .engineignore 否定规则永远无法解除这些目录的跳过。
SAFETY_CORE_DIRS = frozenset({".git", "node_modules", ".worktrees", ".claude-worktrees"})

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    "vendor",
    "target",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
    "Pods",
    ".idea",
    ".vscode",
    "__snapshots__",
}

# 对照原生引擎 discover：代码 + Markdown/配置等都会进图
CODE_EXT = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".scala",
    ".vue",
    ".svelte",
}
DOC_EXT = {".md", ".mdx", ".markdown", ".rst"}
CONFIG_EXT = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".sql",
    ".graphql",
    ".gql",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".less",
    ".xml",
    ".tf",
    ".proto",
}
ALL_EXT = CODE_EXT | DOC_EXT | CONFIG_EXT

MODE_LIMITS = {
    # fast：少文件，仍含 md Section（否则节点数会严重偏低）
    "fast": {"max_files": 800, "max_bytes": 400_000, "layout_iters": 0},
    "moderate": {"max_files": 8_000, "max_bytes": 1_500_000, "layout_iters": 0},
    # full：对齐原生引擎 量级；服务端不做力导向
    "full": {"max_files": 100_000, "max_bytes": 5_000_000, "layout_iters": 0},
    "cross-repo-intelligence": {"max_files": 0, "max_bytes": 0, "layout_iters": 0},
}

MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
MD_SETEXT_RE = re.compile(r"^(.+)\n(=+|-+)\s*$", re.M)
JS_INTERFACE_RE = re.compile(
    r"(?:export\s+)?interface\s+([A-Za-z_][\w$]*)",
)
JS_TYPE_RE = re.compile(
    r"(?:export\s+)?type\s+([A-Za-z_][\w$]*)\s*=",
)
JS_CLASS_RE = re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_][\w$]*)")
JS_FN_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_][\w$]*)\s*\(",
)
JS_ARROW_RE = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_][\w$]*)\s*=>",
)
JS_VAR_RE = re.compile(
    # 仅列首声明 = 模块顶层（对齐原生引擎 Variable，避免缩进 const 爆炸）
    r"(?m)^(export\s+)?(?:const|let|var)\s+([A-Za-z_][\w$]*)\s*=",
)
JS_METHOD_RE = re.compile(
    # class 体内缩进方法（启发式，对齐原生引擎 Method 量级）
    r"(?m)^[ \t]{2,8}(?:async\s+)?(?:static\s+)?(?:async\s+)?(?:get|set\s+)?([A-Za-z_][\w$]*)\s*\([^)]*\)\s*\{",
)
JS_IMPORT_RE = re.compile(
    r"""(?:from\s+['"]([^'"]+)['"]|import\s+.*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))"""
)
GO_FN_RE = re.compile(r"func\s+(?:\([^)]+\)\s*)?([A-Za-z_][\w]*)\s*\(")
GO_TYPE_RE = re.compile(r"type\s+([A-Za-z_][\w]*)\s+(?:struct|interface|func|=)")
RS_FN_RE = re.compile(r"(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)\s*[<(]")
RS_STRUCT_RE = re.compile(r"(?:pub\s+)?(?:struct|enum|trait|type)\s+([A-Za-z_][\w]*)")
JAVA_CLASS_RE = re.compile(
    r"(?:public|protected|private|abstract|final|\s)*\s*(?:class|interface|enum|record)\s+([A-Za-z_][\w]*)"
)
JAVA_FN_RE = re.compile(
    r"(?:public|private|protected|static|\s)+\s+[\w<>\[\]]+\s+([A-Za-z_][\w]*)\s*\("
)
CALL_RE = re.compile(r"\b([A-Za-z_][\w$]*)\s*\(")
PY_ROUTE_RE = re.compile(
    r"""@(?:\w+\.)?(?:get|post|put|patch|delete|route|api_route|head|options)\(\s*['"]([^'"]+)['"]""",
    re.I,
)
JS_ROUTE_RE = re.compile(
    r"""(?:\.(?:get|post|put|patch|delete|use|all)|router\.(?:get|post|put|patch|delete|use))\(\s*['"`]([^'"`]+)['"`]""",
    re.I,
)
ENV_ASSIGN_RE = re.compile(
    r"""(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]{1,64})\s*=\s*["']?([^\s#'"]+)"""
)
ENV_USAGE_RE = re.compile(
    r"""(?:os\.environ(?:\.get)?|os\.getenv|process\.env)\[['\"]([A-Z][A-Z0-9_]{1,64})['\"]\]|"""
    r"""(?:os\.environ\.get|os\.getenv)\(\s*['\"]([A-Z][A-Z0-9_]{1,64})['\"]"""
    r"""|process\.env\.([A-Z][A-Z0-9_]{1,64})"""
)
DECORATOR_NAME_RE = re.compile(r"^@([\w\.]+)")


def _nid(project: str, qn: str) -> str:
    h = hashlib.sha1(f"{project}:{qn}".encode()).hexdigest()[:16]
    return f"n_{h}"


def _module_qn(project: str, rel: str) -> str:
    """对齐原生引擎 ModuleQN：project.path.to.file（保留 __init__）。"""
    norm = rel.replace("\\", "/").removesuffix("/")
    parts = [project] + [p for p in norm.split("/") if p]
    return ".".join(parts)


def _folder_qn(project: str, rel_dir: str) -> str:
    if not rel_dir or rel_dir in (".", "/"):
        return project
    return ".".join([project] + [p for p in rel_dir.replace("\\", "/").split("/") if p])


def _file_qn(project: str, rel: str) -> str:
    return _module_qn(project, rel) + ".__file__"


def _complexity_attrs(source: str) -> dict:
    loops = len(re.findall(r"\b(for|while|foreach)\b", source))
    branches = len(re.findall(r"\b(if|elif|else|switch|case|catch)\b", source))
    recursion_hint = 1 if "self." in source or re.search(r"\breturn\s+\w+\(", source) else 0
    alloc_in_loop = 1 if loops and re.search(r"(new |malloc|alloc|\[\]|list\()", source) else 0
    return {
        "cyclomatic_complexity": max(1, branches + loops),
        "cognitive_complexity": max(1, branches + loops * 2),
        "loop_depth": min(5, loops),
        "transitive_loop_depth": min(5, loops),
        "linear_scan_in_loop": 1 if loops else 0,
        "alloc_in_loop": alloc_in_loop,
        "unguarded_recursion": recursion_hint,
    }


def _read_git_branch(root: Path) -> str:
    head = root / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "HEAD"
    if text.startswith("ref:"):
        return text.split("/")[-1] or "HEAD"
    return text[:12] or "HEAD"


def iter_source_files(root: Path, max_files: int) -> Iterable[Path]:
    ignore_rules = _load_engineignore(root)
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_root = Path(dirpath)
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIRS
            and not (
                d.startswith(".")
                and d not in SAFETY_CORE_DIRS
                and not _negated_by(ignore_rules, root, rel_root / d, is_dir=True)
            )
            and not _ignored_by(ignore_rules, root, rel_root / d, is_dir=True)
        ]
        for name in filenames:
            rel_path = rel_root / name
            if _ignored_by(ignore_rules, root, rel_path, is_dir=False):
                continue
            ext = Path(name).suffix.lower()
            # .env / Dockerfile 无后缀也收
            low = name.lower()
            if (
                ext not in ALL_EXT
                and low not in {".env", "dockerfile", "makefile"}
                and not low.startswith(".env.")
                and not low.startswith("dockerfile")
            ):
                continue
            yield rel_path
            count += 1
            if max_files > 0 and count >= max_files:
                return


def _load_engineignore(root: Path) -> list[tuple[str, bool]]:
    """解析仓库根 .engineignore（gitignore 风格）：返回 (pattern, negated)。

    仅支持仓库根单文件（与 C 引擎一致）；# 注释、! 否定、行尾空白忽略。
    否定规则可解除普通忽略，但无法解除 SAFETY_CORE_DIRS（见 _negated_by）。
    """
    rules: list[tuple[str, bool]] = []
    ignore_file = root / ".engineignore"
    if not ignore_file.is_file():
        return rules
    try:
        lines = ignore_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rules
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            rules.append((line[1:].lstrip("/"), True))
        else:
            rules.append((line.lstrip("/"), False))
    return rules


def _rel_posix(repo_root: Path, path: Path) -> str:
    """把路径转为相对仓库根的 posix 路径（.engineignore pattern 的匹配基准）。"""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _ignored_by(
    rules: list[tuple[str, bool]], repo_root: Path, path: Path, *, is_dir: bool
) -> bool:
    """是否被 .engineignore 忽略。最后一条匹配规则生效（gitignore 语义）。"""
    # 若被 safety-core 覆盖，绝不允许否定解除
    if is_dir and path.name in SAFETY_CORE_DIRS:
        return True
    rel = _rel_posix(repo_root, path)
    verdict = False
    for pattern, negated in rules:
        if _pattern_match(pattern, rel, is_dir):
            verdict = not negated
    return verdict


def _negated_by(
    rules: list[tuple[str, bool]], repo_root: Path, path: Path, *, is_dir: bool
) -> bool:
    """路径是否被 .engineignore 否定规则解除忽略（用于隐藏目录的放行判断）。"""
    if path.name in SAFETY_CORE_DIRS:
        return False
    rel = _rel_posix(repo_root, path)
    verdict = False
    for pattern, negated in rules:
        if negated and _pattern_match(pattern, rel, is_dir):
            verdict = True
    return verdict


def _pattern_match(pattern: str, rel: str, is_dir: bool) -> bool:
    """gitignore 风格匹配（rel 为相对仓库根的 posix 路径）。

    - 目录限定 pattern 以 / 结尾（如 `build/`）：匹配该目录及其下所有内容
    - 无 / 的 pattern：匹配任意层级的 basename（如 `*.log`）
    - 含 / 的 pattern：锚定相对仓库根路径
    """
    dir_only = pattern.endswith("/")
    pat = pattern.rstrip("/")
    if "/" not in pat:
        return fnmatch.fnmatch(Path(rel).name, pat)
    # 含 /：锚定相对根
    if dir_only:
        return rel == pat or rel.startswith(pat + "/")
    return fnmatch.fnmatch(rel, pat)


def index_repository(
    store: GraphStore,
    repo_path: str | Path,
    *,
    mode: str = "moderate",
) -> dict:
    limits = MODE_LIMITS.get(mode) or MODE_LIMITS["moderate"]
    root = Path(repo_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"仓库路径不存在: {root}")

    store.clear()
    store.meta = {"mode": mode, "repo_path": str(root)}

    files = list(iter_source_files(root, limits["max_files"]))
    max_bytes = int(limits["max_bytes"] or 0)

    # —— Pass 1: 结构（Project / Branch / Folder / File）——
    project_qn = store.project
    project_id = _nid(store.project, f"Project:{project_qn}")
    store.add_node(
        Node(
            id=project_id,
            name=store.project,
            label="Project",
            qualified_name=project_qn,
        )
    )
    branch = _read_git_branch(root)
    branch_qn = f"{project_qn}.__branch__.{branch}"
    branch_id = _nid(store.project, branch_qn)
    store.add_node(
        Node(
            id=branch_id,
            name=branch,
            label="Branch",
            qualified_name=branch_qn,
        )
    )
    store.add_edge(Edge(source=project_id, target=branch_id, type="HAS_BRANCH"))

    folder_ids: dict[str, str] = {"": project_id, ".": project_id}
    file_ids: dict[str, str] = {}
    module_ids: dict[str, str] = {}
    qn_to_id: dict[str, str] = {project_qn: project_id}
    call_sites: list[tuple[str, str]] = []
    import_edges: list[tuple[str, str]] = []  # (module_id, target_str)

    dirs: set[str] = set()
    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent in (".", ""):
            continue
        cur = parent
        while cur and cur not in (".", "/"):
            dirs.add(cur)
            nxt = str(Path(cur).parent).replace("\\", "/")
            if nxt in (".", cur):
                break
            cur = nxt

    for d in sorted(dirs, key=lambda x: x.count("/")):
        fq = _folder_qn(store.project, d)
        fid = _nid(store.project, f"Folder:{fq}")
        folder_ids[d] = fid
        store.add_node(
            Node(
                id=fid,
                name=Path(d).name,
                label="Folder",
                file_path=d,
                qualified_name=fq,
            )
        )
        qn_to_id[fq] = fid
        parent = str(Path(d).parent).replace("\\", "/")
        parent_id = folder_ids.get(parent if parent not in (".",) else "", project_id)
        store.add_edge(Edge(source=parent_id, target=fid, type="CONTAINS_FOLDER"))

    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if max_bytes > 0 and len(raw) > max_bytes:
            raw = raw[:max_bytes]
        text = raw.decode("utf-8", errors="replace")

        file_qn = _file_qn(store.project, rel)
        fid = _nid(store.project, file_qn)
        ext = path.suffix.lower()
        store.add_node(
            Node(
                id=fid,
                name=path.name,
                label="File",
                file_path=rel,
                qualified_name=file_qn,
                attrs={
                    "extension": ext,
                    "language": _lang_of(ext, path.name),
                    "is_test": _is_test_path(rel),
                },
            )
        )
        file_ids[rel] = fid
        qn_to_id[file_qn] = fid
        parent = str(Path(rel).parent).replace("\\", "/")
        parent_id = folder_ids.get("" if parent == "." else parent, project_id)
        store.add_edge(Edge(source=parent_id, target=fid, type="CONTAINS_FILE"))

        # Module（每个可解析文件一个，对齐原生引擎）
        mod_qn = _module_qn(store.project, rel)
        mid = _nid(store.project, f"Module:{mod_qn}")
        store.add_node(
            Node(
                id=mid,
                name=path.name,
                label="Module",
                file_path=rel,
                qualified_name=mod_qn,
            )
        )
        module_ids[rel] = mid
        qn_to_id[mod_qn] = mid
        store.add_edge(Edge(source=fid, target=mid, type="DEFINES"))

        if ext in DOC_EXT:
            _index_markdown(store, text, rel, mid, qn_to_id)
        elif ext in {".py", ".pyi"}:
            _index_python(
                store, text, rel, mid, qn_to_id, call_sites, import_edges
            )
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            _index_js_ts(
                store, text, rel, mid, qn_to_id, call_sites, import_edges, ext
            )
        elif ext == ".go":
            _index_go(store, text, rel, mid, qn_to_id, call_sites)
        elif ext == ".rs":
            _index_regex_defs(
                store,
                text,
                rel,
                mid,
                qn_to_id,
                call_sites,
                fn_re=RS_FN_RE,
                type_re=RS_STRUCT_RE,
                type_label="Type",
            )
        elif ext in {".java", ".kt", ".kts"}:
            _index_regex_defs(
                store,
                text,
                rel,
                mid,
                qn_to_id,
                call_sites,
                fn_re=JAVA_FN_RE,
                type_re=JAVA_CLASS_RE,
                type_label="Class",
            )
        else:
            # 配置等：仍保留 File+Module；再扫 Env
            pass

        _index_routes(store, text, rel, mid, qn_to_id, ext)
        _index_env_usages(store, text, mid, qn_to_id)

    # Env 文件扫描（对照 envscan）
    for path in files:
        name = path.name.lower()
        if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
            rel = str(path.relative_to(root)).replace("\\", "/")
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            mid = module_ids.get(rel)
            if mid:
                _index_env_file(store, text, mid, qn_to_id)

    # CALLS
    name_index: dict[str, list[str]] = {}
    for qn, nid in qn_to_id.items():
        short = qn.rsplit(".", 1)[-1]
        name_index.setdefault(short, []).append(nid)

    for caller, callee in call_sites:
        targets = name_index.get(callee) or []
        for tid in targets[:3]:
            if tid != caller:
                store.add_edge(Edge(source=caller, target=tid, type="CALLS"))

    # IMPORTS：未解析到本地模块时不造自环；仅保留可解析到本仓库 Module 的边
    mod_by_suffix: dict[str, str] = {}
    for rel, mid in module_ids.items():
        mod_by_suffix[rel.replace("\\", "/")] = mid
        mod_by_suffix[rel.replace("\\", "/").rsplit(".", 1)[0]] = mid

    for mid, target in import_edges:
        t = target.strip("./")
        # 相对/别名粗匹配
        hit = None
        for key, tid in mod_by_suffix.items():
            if key.endswith(t.replace(".", "/") + ".py") or key.endswith(
                t.replace(".", "/") + ".ts"
            ):
                hit = tid
                break
            if key.replace("/", ".").endswith(t):
                hit = tid
                break
        if hit and hit != mid:
            store.add_edge(Edge(source=mid, target=hit, type="IMPORTS"))

    # CONTAINS：符号挂到 File
    for n in list(store.nodes.values()):
        if (
            n.label
            in (
                "Function",
                "Class",
                "Method",
                "Interface",
                "Type",
                "Variable",
                "Section",
                "Route",
                "Decorator",
            )
            and n.file_path in file_ids
        ):
            store.add_edge(
                Edge(source=file_ids[n.file_path], target=n.id, type="CONTAINS")
            )

    store.rebuild_adj()
    nodes = list(store.nodes.values())
    edges = list(store.edges)
    force_layout_3d(nodes, edges, iterations=limits["layout_iters"])

    return {
        "project": store.project,
        "mode": mode,
        "node_count": len(store.nodes),
        "edge_count": len(store.edges),
        "repo_path": str(root),
    }


def _lang_of(ext: str, name: str) -> str:
    low = name.lower()
    if ext in DOC_EXT:
        return "markdown"
    if ext in {".py", ".pyi"}:
        return "python"
    if ext in {".ts", ".tsx"}:
        return "typescript"
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if low.startswith("dockerfile"):
        return "dockerfile"
    return ext.lstrip(".") or "text"


def _is_test_path(rel: str) -> bool:
    low = rel.lower().replace("\\", "/")
    return (
        "/test/" in f"/{low}"
        or "/tests/" in f"/{low}"
        or low.endswith("_test.py")
        or low.endswith(".test.ts")
        or low.endswith(".test.tsx")
        or low.endswith(".spec.ts")
        or low.endswith("_test.go")
    )


def _index_markdown(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
) -> None:
    """原生引擎：atx/setext heading → Section。"""
    seen: set[str] = set()
    for m in MD_HEADING_RE.finditer(text):
        title = m.group(2).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        line = text[: m.start()].count("\n") + 1
        qn = f"{_module_qn(store.project, rel)}.#{title}"
        nid = _nid(store.project, qn)
        store.add_node(
            Node(
                id=nid,
                name=title[:200],
                label="Section",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line,
                attrs={"level": len(m.group(1))},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))

    for m in MD_SETEXT_RE.finditer(text):
        title = m.group(1).strip()
        if not title or title.startswith("#") or title in seen:
            continue
        seen.add(title)
        line = text[: m.start()].count("\n") + 1
        qn = f"{_module_qn(store.project, rel)}.#{title}"
        nid = _nid(store.project, qn)
        store.add_node(
            Node(
                id=nid,
                name=title[:200],
                label="Section",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line,
                attrs={"level": 1 if m.group(2).startswith("=") else 2},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))


def _index_python(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    call_sites: list[tuple[str, str]],
    import_edges: list[tuple[str, str]],
) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    mod = _module_qn(store.project, rel)

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                raw = (
                    f"{node.module}.{alias.name}"
                    if isinstance(node, ast.ImportFrom) and node.module
                    else alias.name
                )
                import_edges.append((module_id, raw))

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qn = f"{mod}.{'.'.join(self.stack + [node.name])}" if self.stack else f"{mod}.{node.name}"
            nid = _nid(store.project, qn)
            src = ast.get_source_segment(text, node) or ""
            decs = [_decorator_str(d) for d in node.decorator_list]
            store.add_node(
                Node(
                    id=nid,
                    name=node.name,
                    label="Class",
                    file_path=rel,
                    qualified_name=qn,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    attrs={**_complexity_attrs(src), "decorators": decs},
                )
            )
            qn_to_id[qn] = nid
            parent = qn_to_id.get(f"{mod}.{'.'.join(self.stack)}") if self.stack else module_id
            store.add_edge(Edge(source=parent or module_id, target=nid, type="DEFINES"))
            for d in node.decorator_list:
                _add_decorator(store, d, nid, rel, mod, qn_to_id)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._fn(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._fn(node)

        def _fn(self, node: ast.AST) -> None:
            name = getattr(node, "name", "fn")
            if self.stack:
                qn = f"{mod}.{'.'.join(self.stack)}.{name}"
                label = "Method"
            else:
                qn = f"{mod}.{name}"
                label = "Function"
            nid = _nid(store.project, qn)
            src = ast.get_source_segment(text, node) or ""
            decs = [_decorator_str(d) for d in getattr(node, "decorator_list", [])]
            store.add_node(
                Node(
                    id=nid,
                    name=name,
                    label=label,
                    file_path=rel,
                    qualified_name=qn,
                    start_line=getattr(node, "lineno", 0),
                    end_line=getattr(node, "end_lineno", 0) or 0,
                    attrs={**_complexity_attrs(src), "decorators": decs},
                )
            )
            qn_to_id[qn] = nid
            parent = (
                qn_to_id.get(f"{mod}.{'.'.join(self.stack)}") if self.stack else module_id
            )
            store.add_edge(
                Edge(
                    source=parent or module_id,
                    target=nid,
                    type="DEFINES_METHOD" if label == "Method" else "DEFINES",
                )
            )
            for d in getattr(node, "decorator_list", []):
                _add_decorator(store, d, nid, rel, mod, qn_to_id)
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    callee = _call_name(child.func)
                    if callee:
                        call_sites.append((nid, callee))

        def visit_Assign(self, node: ast.Assign) -> None:
            if self.stack:
                return
            for t in node.targets:
                self._var(t, node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if self.stack:
                return
            self._var(node.target, node)

        def _var(self, target: ast.AST, node: ast.AST) -> None:
            if not isinstance(target, ast.Name):
                return
            name = target.id
            # 跳过过于琐碎的模块级绑定，贴近原生引擎对「有意义声明」的偏好
            if name in {"__all__", "__version__", "__author__"}:
                return
            qn = f"{mod}.{name}"
            if qn in qn_to_id:
                return
            nid = _nid(store.project, qn)
            store.add_node(
                Node(
                    id=nid,
                    name=name,
                    label="Variable",
                    file_path=rel,
                    qualified_name=qn,
                    start_line=getattr(node, "lineno", 0),
                    end_line=getattr(node, "end_lineno", 0) or 0,
                    attrs={"is_exported": not name.startswith("_")},
                )
            )
            qn_to_id[qn] = nid
            store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))

    Visitor().visit(tree)


def _decorator_str(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return _decorator_str(node.func)
        return "decorator"


def _add_decorator(
    store: GraphStore,
    dec: ast.AST,
    target_id: str,
    rel: str,
    mod: str,
    qn_to_id: dict[str, str],
) -> None:
    raw = _decorator_str(dec)
    m = DECORATOR_NAME_RE.match("@" + raw if not raw.startswith("@") else raw)
    name = (m.group(1) if m else raw).split("(")[0].strip("@")
    if not name:
        return
    qn = f"{mod}.@decorator.{name}"
    nid = qn_to_id.get(qn) or _nid(store.project, qn)
    if qn not in qn_to_id:
        store.add_node(
            Node(
                id=nid,
                name=name,
                label="Decorator",
                file_path=rel,
                qualified_name=qn,
            )
        )
        qn_to_id[qn] = nid
    store.add_edge(
        Edge(source=nid, target=target_id, type="DECORATES", attrs={"decorator": name})
    )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _index_js_ts(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    call_sites: list[tuple[str, str]],
    import_edges: list[tuple[str, str]],
    ext: str,
) -> None:
    mod = _module_qn(store.project, rel)
    lines = text.splitlines()
    func_names: set[str] = set()

    for m in JS_IMPORT_RE.finditer(text):
        target = m.group(1) or m.group(2) or m.group(3) or ""
        if target:
            import_edges.append((module_id, target))

    def _add(label: str, name: str, start: int, end: int, attrs: dict | None = None) -> str:
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            return qn_to_id[qn]
        nid = _nid(store.project, qn)
        line = text[:start].count("\n") + 1
        store.add_node(
            Node(
                id=nid,
                name=name,
                label=label,
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=max(line, end),
                attrs=attrs or {},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))
        return nid

    if ext in {".ts", ".tsx"}:
        for m in JS_INTERFACE_RE.finditer(text):
            _add("Interface", m.group(1), m.start(), m.end())
        for m in JS_TYPE_RE.finditer(text):
            _add("Type", m.group(1), m.start(), m.end())

    for m in JS_CLASS_RE.finditer(text):
        _add("Class", m.group(1), m.start(), m.end(), _complexity_attrs(""))

    for m in JS_FN_RE.finditer(text):
        name = m.group(1)
        func_names.add(name)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 40])
        nid = _add("Function", name, m.start(), m.end(), _complexity_attrs(chunk))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))

    for m in JS_ARROW_RE.finditer(text):
        name = m.group(1)
        func_names.add(name)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 40])
        nid = _add("Function", name, m.start(), m.end(), _complexity_attrs(chunk))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))

    # Class methods（缩进启发式）
    skip_method = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "return",
    }
    for m in JS_METHOD_RE.finditer(text):
        name = m.group(1)
        if name in skip_method or name in func_names:
            continue
        # 需要前文有 class
        before = text[max(0, m.start() - 800) : m.start()]
        if "class " not in before:
            continue
        func_names.add(name)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 30])
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            continue
        nid = _nid(store.project, qn)
        store.add_node(
            Node(
                id=nid,
                name=name,
                label="Method",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line + 30,
                attrs=_complexity_attrs(chunk),
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES_METHOD"))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))

    for m in JS_VAR_RE.finditer(text):
        name = m.group(2)
        exported = bool(m.group(1))
        if name in func_names or name in {"if", "for", "while", "switch"}:
            continue
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            continue
        _add(
            "Variable",
            name,
            m.start(),
            m.end(),
            {"is_exported": exported},
        )


def _index_go(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    call_sites: list[tuple[str, str]],
) -> None:
    _index_regex_defs(
        store,
        text,
        rel,
        module_id,
        qn_to_id,
        call_sites,
        fn_re=GO_FN_RE,
        type_re=GO_TYPE_RE,
        type_label="Type",
    )


def _index_regex_defs(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    call_sites: list[tuple[str, str]],
    *,
    fn_re: re.Pattern[str],
    type_re: re.Pattern[str] | None,
    type_label: str,
) -> None:
    mod = _module_qn(store.project, rel)
    lines = text.splitlines()
    if type_re:
        for m in type_re.finditer(text):
            name = m.group(1)
            # java interface → Interface
            label = type_label
            ctx = text[max(0, m.start() - 40) : m.start()]
            if "interface" in ctx:
                label = "Interface"
            qn = f"{mod}.{name}"
            if qn in qn_to_id:
                continue
            nid = _nid(store.project, qn)
            line = text[: m.start()].count("\n") + 1
            store.add_node(
                Node(
                    id=nid,
                    name=name,
                    label=label,
                    file_path=rel,
                    qualified_name=qn,
                    start_line=line,
                    end_line=line,
                )
            )
            qn_to_id[qn] = nid
            store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))

    for m in fn_re.finditer(text):
        name = m.group(1)
        if name in {"if", "for", "while", "switch", "catch", "return", "new"}:
            continue
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            continue
        nid = _nid(store.project, qn)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 40])
        store.add_node(
            Node(
                id=nid,
                name=name,
                label="Function",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line + 40,
                attrs=_complexity_attrs(chunk),
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))


def _index_routes(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    ext: str,
) -> None:
    mod = _module_qn(store.project, rel)
    patterns = []
    if ext in {".py", ".pyi"}:
        patterns.append(PY_ROUTE_RE)
    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        patterns.append(JS_ROUTE_RE)
    for cre in patterns:
        for m in cre.finditer(text):
            path = m.group(1)
            qn = f"{mod}.__route__.{path}"
            if qn in qn_to_id:
                continue
            nid = _nid(store.project, qn)
            store.add_node(
                Node(
                    id=nid,
                    name=path,
                    label="Route",
                    file_path=rel,
                    qualified_name=qn,
                    start_line=text[: m.start()].count("\n") + 1,
                    attrs={"path": path},
                )
            )
            qn_to_id[qn] = nid
            store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))


def _index_env_file(
    store: GraphStore,
    text: str,
    module_id: str,
    qn_to_id: dict[str, str],
) -> None:
    for m in ENV_ASSIGN_RE.finditer(text):
        key, val = m.group(1), m.group(2)
        qn = f"env.{key}"
        if qn in qn_to_id:
            continue
        nid = _nid(store.project, qn)
        store.add_node(
            Node(
                id=nid,
                name=key,
                label="EnvVar",
                qualified_name=qn,
                attrs={"value_preview": val[:80]},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))


def _index_env_usages(
    store: GraphStore,
    text: str,
    module_id: str,
    qn_to_id: dict[str, str],
) -> None:
    for m in ENV_USAGE_RE.finditer(text):
        key = m.group(1) or m.group(2) or m.group(3)
        if not key:
            continue
        qn = f"env.{key}"
        if qn not in qn_to_id:
            nid = _nid(store.project, qn)
            store.add_node(
                Node(id=nid, name=key, label="EnvVar", qualified_name=qn)
            )
            qn_to_id[qn] = nid
        store.add_edge(
            Edge(source=module_id, target=qn_to_id[qn], type="USAGE")
        )
