"""插件清单与整包批准能力(§9.13,phase-72)。

发现(list_plugins)对任何已鉴权 actor 只读;批准/撤销(set_plugin_approval)
是装载边界,与 MCP / 敏感设置同权:仅 USER(phase-13 同精神),agent actor 拒绝。
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def _require_user(actor: ActorRef) -> None:
    if actor is None or actor.kind is not ActorKind.USER:
        raise ServiceError("agent", ErrorSuffix.FORBIDDEN, "插件批准/撤销仅限用户操作")


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_plugins",
                description="插件清单(发现 + 批准状态 + contains 计数;未批准不装载)")
    def list_plugins() -> dict:
        return {"items": deps.plugins.list()}

    @capability(reg, name="set_plugin_approval",
                description="整包批准/撤销插件;批准后 skill/hook 即装,MCP 只登记待批准条目",
                cost=1)
    async def set_plugin_approval(name: str, approved: bool, granularity: str = "bundle",
                                  _actor: ActorRef = None) -> dict:
        _require_user(_actor)
        if granularity != "bundle":
            # 本刀只做整包;逐项批准留给 phase-73,不做静默降级
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT,
                               f"本阶段只支持整包批准 granularity='bundle': {granularity!r}")
        if approved:
            return await deps.plugins.approve(name, _actor)
        return await deps.plugins.unapprove(name, _actor)
