"""确保同仓服务路径可导入（agent_core / graph_fallback 等）。

薄壳：服务路径集合的单一权威定义在 py_shared.repo_paths，
此处仅做最小引导（定位并插入 py-shared 目录）后转发调用，
避免服务路径清单在 api/agent/pytest 多处漂移。
"""
from __future__ import annotations

import sys
from pathlib import Path

# services/api/api_backend/path_setup.py → parents[3] = 仓库根
_PY_SHARED = Path(__file__).resolve().parents[3] / "packages" / "py-shared"
_PY_SHARED_STR = str(_PY_SHARED)
if _PY_SHARED_STR not in sys.path:
    sys.path.insert(0, _PY_SHARED_STR)

from py_shared.repo_paths import ensure_service_paths  # noqa: E402

ensure_service_paths()
