"""Python 回退引擎(移植自旧 graph_fallback,§8.4 决策 6:C 不可用时回退)。

纯 Python(ast/正则),无外部依赖;统一 `call(name, args)` 分派。
"""

from .engine import GraphEngine, get_engine

__all__ = ["GraphEngine", "get_engine"]
