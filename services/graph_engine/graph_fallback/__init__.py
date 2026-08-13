"""
Voyager 图谱引擎 Python 回退层。

默认运行时为迁入的 C 引擎 sidecar（services/graph_engine/graph_engine_core）。
本包仅在 sidecar 不可用时使用。
"""

from .engine import GraphEngine, get_engine

__all__ = ["GraphEngine", "get_engine"]
