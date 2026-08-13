"""
ORM 模型 —— 项目相关（本地单机，无 user 维度）

权威实现在 py_shared.models.project，此处 re-export 兼容既有 import。
"""
from py_shared.models.project import *  # noqa: F401, F403
from py_shared.models.project import Project, Tag, project_tags  # noqa: F401
