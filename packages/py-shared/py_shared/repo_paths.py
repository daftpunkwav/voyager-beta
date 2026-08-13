"""同仓服务路径引导（单一权威入口）。

api_backend / agent_runtime / pytest 三处此前各维护一份 sys.path 清单，
必然漂移（曾漏 services/graph_engine 导致独立 agent 进程 ModuleNotFoundError）。
本模块是唯一路径集合定义：调用方只需先定位并插入 py-shared 目录，
再 import 本模块调用 ensure_service_paths()。
"""
from __future__ import annotations

import sys
from pathlib import Path

# packages/py-shared/py_shared/repo_paths.py → parents[3] = 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[3]

# 同仓服务路径（按依赖方向排列；py_shared 自身由调用方引导插入）
_SERVICE_DIRS = (
    "services/api",
    "services/agent",
    "services/graph_engine",
    "packages/py-shared",
)


def ensure_service_paths() -> None:
    """把全部同仓服务目录插入 sys.path（幂等）。"""
    for rel in _SERVICE_DIRS:
        path = _REPO_ROOT / rel
        if not path.is_dir():
            continue
        s = str(path)
        if s not in sys.path:
            sys.path.insert(0, s)


def bootstrap_py_shared() -> None:
    """最小引导：仅把 py-shared 目录插入 sys.path（调用方必须最先执行）。"""
    s = str(_REPO_ROOT / "packages" / "py-shared")
    if s not in sys.path:
        sys.path.insert(0, s)
