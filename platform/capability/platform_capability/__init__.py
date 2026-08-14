"""能力框架:一次定义 → REST + MCP 双生成;入口强制鉴权/限流/审计。"""

from platform_capability.define import Capability, capability, coerce_input
from platform_capability.gen_mcp import build_server, build_tool_specs, dataclass_to_json_schema
from platform_capability.gen_rest import build_router
from platform_capability.guards import (
    SENSITIVE_KEYS,
    AuditEntry,
    AuditSink,
    CallRequest,
    CostQuota,
    InMemoryAuditSink,
    LocalAuth,
    execute,
    summarize_args,
)
from platform_capability.registry import Registry

__all__ = [
    "SENSITIVE_KEYS",
    "AuditEntry",
    "AuditSink",
    "CallRequest",
    "Capability",
    "CostQuota",
    "InMemoryAuditSink",
    "LocalAuth",
    "Registry",
    "build_router",
    "build_server",
    "build_tool_specs",
    "capability",
    "coerce_input",
    "dataclass_to_json_schema",
    "execute",
    "summarize_args",
]
