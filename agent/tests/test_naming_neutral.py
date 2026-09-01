"""命名中性扫描:agent/ 生产源码禁止出现品牌名 voyager。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND_RE = re.compile(r"voyager", re.IGNORECASE)


def scan_source_files(root: Path) -> list[str]:
    """扫描 root 下生产 .py,返回每条命中信息: 路径:行号:内容。"""
    hits: list[str] = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if BRAND_RE.search(line):
                rel = path.relative_to(root)
                hits.append(f"{rel}:{lineno}:{line.strip()}")
    return hits


def test_no_brand_in_production_source() -> None:
    """agent/ 生产 .py 中不能出现 voyager 字符串。"""
    hits = scan_source_files(ROOT)
    if hits:
        raise AssertionError("发现生产源码含品牌名 voyager:\n" + "\n".join(hits))


def test_scanner_catches_deliberate_dirty_string() -> None:
    """用内存脏字符串证明扫描器会命中。"""
    dirty = "# old name was Voyager-Agent, do not use\n"
    assert BRAND_RE.search(dirty)
