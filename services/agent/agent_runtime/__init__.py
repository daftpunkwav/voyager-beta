"""
Agent 运行时包。

阶段 4 起 Agent 执行逻辑（SSE 编排 / 流控 / 持久化副作用）已迁入 execution.py，
EmbeddedAgentRuntime（runtime.py）作为 api_backend 的 Embedded Adapter 委托到
agent_core（Hub/ReAct/记忆/工具）与本包 execution。

依赖方向：agent_core 只依赖 packages/py-shared 的 Protocol；本包（运行层）
在宿主（api_backend / 独立进程入口）注入业务服务契约后运行。
"""

__version__ = "0.3.0"
