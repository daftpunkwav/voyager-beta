"""自研图谱引擎：索引 / 搜索 / schema 冒烟。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graph_fallback import GraphEngine


def test_index_and_search_python_repo():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "pkg").mkdir()
        (root / "pkg" / "mod.py").write_text(
            "def hello(x):\n    return world(x)\n\ndef world(x):\n    return x\n",
            encoding="utf-8",
        )
        eng = GraphEngine(data_root=root / "data")
        out = eng.index_repository(str(root), mode="fast", name="graph-test", persistence=True)
        assert out["node_count"] > 0
        schema = eng.get_graph_schema("graph-test")
        assert schema["node_labels"]
        hits = eng.search_graph("graph-test", query="hello", limit=20)
        assert hits["results"]
        assert hits["has_more"] is False or isinstance(hits["has_more"], bool)
        layout = eng.fetch_layout("graph-test", max_nodes=100)
        assert layout["nodes"]
        arch = eng.get_architecture("graph-test")
        assert "packages" in arch
        db = root / "data" / "graph-db" / "graph-test.db"
        assert db.exists()


def test_index_respects_engineignore():
    """SEC-005 回归：Python 回退引擎必须遵守 .engineignore（gitignore 风格），
    且 SAFETY_CORE_DIRS（如 node_modules）不可被否定规则解除。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".engineignore").write_text("skip_me/\n*.tmp\n", encoding="utf-8")
        (root / "keep.py").write_text("def kept():\n    return 1\n")
        (root / "skip_me").mkdir()
        (root / "skip_me" / "inner.py").write_text("def inner():\n    return 2\n")
        (root / "junk.tmp").write_text("z")
        eng = GraphEngine(data_root=root / "data")
        out = eng.index_repository(str(root), mode="fast", name="ei-test", persistence=True)
        assert out["node_count"] > 0
        # skip_me/ 与 *.tmp 的内容不应进图
        hits = eng.search_graph("ei-test", query="kept", limit=20)
        assert hits["results"], "keep.py 应被索引"
        hits_inner = eng.search_graph("ei-test", query="inner", limit=20)
        assert not any("inner" in (r.get("name") or "").lower() for r in hits_inner["results"]),             "skip_me/ 内容不应被索引（.engineignore）"


def test_engineignore_safety_core_not_negatable():
    """SEC-005：SAFETY_CORE_DIRS（node_modules）不可被 .engineignore 否定解除。"""
    from graph_fallback.indexer import _ignored_by, _load_engineignore

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".engineignore").write_text("!node_modules/\n", encoding="utf-8")
        rules = _load_engineignore(root)
        assert _ignored_by(rules, root, root / "node_modules", is_dir=True)
