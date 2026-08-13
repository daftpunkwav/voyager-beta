"""
ORM 模型 —— 本机应用状态（单行，无用户概念）

权威实现在 py_shared.models.app_state，此处 re-export 兼容既有 import。
"""
from py_shared.models.app_state import *  # noqa: F401, F403
from py_shared.models.app_state import APP_STATE_ID, AppState  # noqa: F401
