""".engineignore(gitignore 风格)解析、匹配与仓库文件遍历。

非可否定的安全核心目录(constants.SAFETY_CORE_DIRS)任何规则都放不进来,
与 C 引擎 discover.c is_safety_core_dir 对齐。
"""
from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from pathlib import Path

from .constants import ALL_EXT, SAFETY_CORE_DIRS, SKIP_DIRS


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
    """解析仓库根 .engineignore：返回 (pattern, negated)。

    仅支持仓库根单文件（与 C 引擎一致）；# 注释、! 否定、行尾空白忽略。
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
    """是否被 .engineignore 忽略。最后一条匹配规则生效（gitignore 语义）。

    safety-core 目录绝不允许被否定规则解除。
    """
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
    """路径是否被否定规则解除忽略(用于隐藏目录的放行判断)。"""
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
