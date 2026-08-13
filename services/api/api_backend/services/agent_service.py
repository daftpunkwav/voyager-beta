"""Agent 会话与对话业务逻辑 —— 阶段 4 已移至 agent_runtime.execution。

本文件保留为 re-export 壳，兼容既有 import（api 路由 / sqlalchemy_adapters / 测试）。
执行逻辑（流控 / SSE 编排 / 持久化副作用）统一由 agent_runtime.execution 提供，
api_backend 经此壳或 AgentRuntimeInterface 调用，不再直接 import agent_core。
注：仅 re-export 公共 API；下划线前缀内部符号请直接从 agent_runtime.execution 引用。
"""
from agent_runtime.execution import (  # noqa: F401
    MAX_SESSION_PROJECTS,
    add_session_project,
    append_message,
    create_session,
    delete_session,
    get_context_window,
    get_session_detail,
    get_session_project_ids,
    list_sessions,
    message_to_out,
    remove_session_project,
    session_to_out,
    set_session_projects,
    stream_analyze,
    stream_chat,
    stream_classify_project,
    stream_generate_note,
    stream_graph_guide,
    stream_import_assist,
    stream_question_answer,
    stream_trending_scout,
    update_session,
)
