"""Graph 运行层：job 管理 / C-py fallback / sidecar 生命周期。

graph_engine_runtime 承接原 api_backend 的 graph 服务职责（阶段 3 迁移）：
- client.py         : GraphEngineClient（C sidecar 优先，Python graph_fallback 回退）
- index_pipeline.py : 索引 job 状态机（浅克隆 → 引擎索引 → 写回）
- sidecar.py        : C 引擎 sidecar 生命周期（健康检查/按需拉起）
- runtime.py        : GraphRuntimeInterface + EmbeddedGraphRuntime（宿主注入）
- context.py        : GraphRuntimeContext（全部外部依赖，宿主 api_backend 注入）

依赖方向：graph_engine_runtime 不 import api_backend；只依赖 py-shared 与 graph_fallback。
"""

from graph_engine_runtime.runtime import EmbeddedGraphRuntime, GraphRuntimeInterface

__all__ = ["EmbeddedGraphRuntime", "GraphRuntimeInterface"]
