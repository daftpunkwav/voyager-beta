"""import 边界扫描(§12 依赖矩阵的自动锁,phase-14)。

AST 级静态检查,零第三方依赖;范围 agent/、services/、platform/(含各自
tests)。deploy/ 不扫:装配根(§13.1)是唯一允许 import 各服务的地方;
apps/、docs/ 不在本锁范围。规则只看 Import/ImportFrom 的完整模块名,
相对导入(level>0)不受约束。
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = ("agent", "services", "platform")
_SKIP_DIRS = {"__pycache__", "venv", ".venv", "node_modules"}


def _imported_modules(tree: ast.AST):
    """(行号, 模块全名) 流;仅顶层绝对导入。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def _violations(scope: tuple[str, ...], source: str, display: str) -> list[str]:
    """按文件所处范围判违规;返回「路径:行号: 原因」列表。

    - agent 内:禁止 services / deploy;
    - services.<域> 内:禁止 agent / deploy / apps,且禁止 services.<另一域>
      (本域 services.<域>.* 放行);
    - platform 内:禁止 agent / services / deploy / apps。
    """
    problems: list[str] = []
    tree = ast.parse(source, filename=display)
    for lineno, module in _imported_modules(tree):
        parts = module.split(".")
        top, second = parts[0], (parts[1] if len(parts) > 1 else "")
        why = ""
        if scope[0] == "agent":
            if top in ("services", "deploy"):
                why = f"agent 禁止 import {top}"
        elif scope[0] == "services":
            domain = scope[1] if len(scope) > 1 else ""
            if top in ("agent", "deploy", "apps"):
                why = f"services.{domain or '*'} 禁止 import {top}"
            elif top == "services" and second != domain:
                why = (f"services.{domain or '*'} 禁止 import "
                       f"services.{second or '*'}(跨域)")
        elif scope[0] == "platform":
            if top in ("agent", "services", "deploy", "apps"):
                why = f"platform 禁止 import {top}"
        if why:
            problems.append(f"{display}:{lineno}: {why}")
    return problems


def _repo_py_files() -> list[Path]:
    out: list[Path] = []
    for root in _SCAN_ROOTS:
        for p in (ROOT / root).rglob("*.py"):
            if _SKIP_DIRS & set(p.parts):
                continue
            out.append(p)
    return sorted(out)


def test_current_repo_has_zero_violations() -> None:
    problems: list[str] = []
    for path in _repo_py_files():
        rel = path.relative_to(ROOT)
        # services 需要域段(services/<域>/...)判跨域;agent/platform 取首段
        scope = rel.parts[:2] if rel.parts[0] == "services" else rel.parts[:1]
        problems.extend(
            _violations(scope, path.read_text(encoding="utf-8"), rel.as_posix()))
    assert not problems, "发现跨边界 import(§12 依赖矩阵):\n" + "\n".join(problems)


def test_checker_catches_deliberate_bad_imports() -> None:
    """锁本身的健全性:合成坏 import 必须被抓到(不往生产文件写坏 import)。"""
    assert len(_violations(("agent",), "import services.gateway\n", "f.py")) == 1
    assert len(_violations(("agent",), "from deploy.bridge import x\n", "f.py")) == 1
    assert len(_violations(("platform",),
                           "from services.notes.wiring import wire\n", "f.py")) == 1
    assert len(_violations(("platform",),
                           "import apps.web\n", "f.py")) == 1
    # services.<域>:邻域违规;本域(含深层模块)放行
    assert len(_violations(("services", "sources"),
                           "from services.graph.store import GraphStore\n",
                           "f.py")) == 1
    assert _violations(("services", "sources"),
                       "from services.sources.modules.doc import store\n",
                       "f.py") == []
    # 失败信息带路径与行号
    msg = _violations(("agent",), "import services\n", "agent/bad.py")[0]
    assert "agent/bad.py" in msg and ":1:" in msg
