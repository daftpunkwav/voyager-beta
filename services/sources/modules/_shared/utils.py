"""sources 服务内共享工具:避免同服务 store 模块重复实现。

跨服务仍保持就近实现;本模块只收敛 sources 内部重复。
"""

from __future__ import annotations

_TAG_CHARS = set("[]\"\\,")


def escape_like(s: str) -> str:
    """LIKE 模式转义:反斜杠/%/_。"""
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def valid_tag(tag: str) -> bool:
    """标签字符约束:非空、≤32 字、不含 json 数组保留字符。"""
    return bool(tag) and len(tag) <= 32 and not (_TAG_CHARS & set(tag))
