"""
跨服务共享的 Pydantic 模型、常量、工具函数。

拆分 Agent / MCP 独立进程后，避免 api 与 agent 互相 import，
将公共契约放在此包。
"""

__version__ = "0.1.0"
