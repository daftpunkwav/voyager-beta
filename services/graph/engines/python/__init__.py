"""Python 回退引擎(移植自旧 graph_fallback,§8.4 决策 6:C 不可用时回退)。

纯 Python(ast/正则),无外部依赖;统一 `call(name, args)` 分派。
引擎不设全局单例(M12):各装配点直接构造实例,测试间零状态泄漏。
"""

from .engine import GraphEngine

__all__ = ["GraphEngine"]
