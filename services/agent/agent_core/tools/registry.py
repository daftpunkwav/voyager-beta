"""工具注册表"""
from __future__ import annotations

import asyncio
import logging
import threading  # §4.2.10 registry 锁
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

ToolHandler = Callable[..., Awaitable[Any]]

# 工具名 → 所需用户权限键（对应 agent_permissions / AgentPermissionsOut）
# 未列出的工具不校验权限开关
TOOL_PERMISSION_MAP: dict[str, str] = {
    "fetch_github_repo": "allow_github_api",
    "fetch_readme": "allow_github_api",
    "create_note": "allow_note_write",
    "update_note": "allow_note_write",
    "ensure_category": "allow_project_write",
    "set_project_category": "allow_project_write",
    "ensure_tags": "allow_project_write",
    "set_project_tags": "allow_project_write",
    "update_project_progress": "allow_project_write",
    "import_github_repos": "allow_project_write",
}

# 权限默认值（与 AgentPermissionsOut 对齐）
_PERMISSION_DEFAULTS: dict[str, bool] = {
    "allow_web_search": True,
    "allow_github_api": True,
    "allow_file_write": False,
    "allow_note_write": True,
    "allow_project_write": True,
}


def _permission_allowed(permissions: dict[str, Any] | None, key: str) -> bool:
    default = _PERMISSION_DEFAULTS.get(key, True)
    if not permissions:
        return default
    if key not in permissions:
        return default
    return bool(permissions[key])


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    allowed_agents: list[str] = field(default_factory=list)
    timeout_ms: int = 30_000
    required_permission: str | None = None

    def to_openai_format(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        # §4.2.10: 注册路径并发保护
        self._lock = threading.RLock()

    def register(self, tool: ToolDefinition) -> None:
        with self._lock:
            self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_tools_for_agent(self, agent_id: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if agent_id in t.allowed_agents or "*" in t.allowed_agents]

    def get_timeout(self, name: str) -> int:
        t = self._tools.get(name)
        return t.timeout_ms if t else 30_000

    def openai_tools_for(self, agent_id: str) -> list[dict[str, Any]]:
        return [t.to_openai_format() for t in self.get_tools_for_agent(agent_id)]

    async def execute(
        self, name: str, args: dict[str, Any], context: Any
    ) -> Any:
        tool = self._tools.get(name)
        if not tool:
            return {
                "code": "AGENT_TOOL_FAILED",
                "error": f"工具 {name} 不存在",
            }
        agent_id = getattr(context, "agent_id", None)
        if agent_id and agent_id not in tool.allowed_agents and "*" not in tool.allowed_agents:
            return {
                "code": "AGENT_TOOL_DENIED",
                "error": f"Agent {agent_id} 无权使用工具 {name}",
            }
        perm_key = tool.required_permission or TOOL_PERMISSION_MAP.get(name)
        if perm_key:
            permissions = getattr(context, "permissions", None) or {}
            if not _permission_allowed(permissions, perm_key):
                return {
                    "code": "AGENT_TOOL_DENIED",
                    "error": f"权限不足：当前设置禁止 {perm_key}，无法调用工具 {name}",
                }
        timeout = tool.timeout_ms / 1000.0
        try:
            return await asyncio.wait_for(
                tool.handler(context=context, **args),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"code": "AGENT_TOOL_TIMEOUT", "error": f"工具 {name} 超时"}
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return {"code": "AGENT_TOOL_FAILED", "error": f"工具 {name} 失败: {e}"}


# 全局单例，builtin 工具在模块导入时注册
global_registry = ToolRegistry()


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    allowed_agents: list[str],
    timeout_ms: int = 30_000,
    required_permission: str | None = None,
):
    def decorator(func: ToolHandler):
        global_registry.register(
            ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                handler=func,
                allowed_agents=allowed_agents,
                timeout_ms=timeout_ms,
                required_permission=required_permission or TOOL_PERMISSION_MAP.get(name),
            )
        )
        return func

    return decorator
