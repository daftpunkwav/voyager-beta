"""插件清单与批准能力(§9.13,phase-72 整包 / phase-74 分项)。

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
                description="插件清单(发现 + 批准状态 + contains 计数与 skill/hook/MCP 明细;"
                            "未批准不装载)")
    def list_plugins() -> dict:
        return {"items": deps.plugins.list()}

    @capability(reg, name="set_plugin_approval",
                description="批准/撤销插件。granularity='bundle' 整包(三类全装,MCP 只登记"
                            "待批准);granularity='item' 分项:只装载勾选的 skills/hooks/mcp"
                            "列表(或 '*' 全选),空勾选拒绝,勾了但清单没有的名字跳过并返回"
                            "skipped。撤销清全部勾选并热卸,且回收该插件登记、尚未批准任何"
                            "工具的外接 MCP(工具已批准或他插件仍在用的保留,结果在"
                            "mcp_reclaimed / mcp_reclaim_skipped 披露)。MCP 工具仍需在外接"
                            "MCP 里批准",
                cost=1)
    async def set_plugin_approval(name: str, approved: bool, granularity: str = "bundle",
                                  skills: object = None, hooks: object = None,
                                  mcp: object = None,
                                  _actor: ActorRef = None) -> dict:
        _require_user(_actor)
        if granularity not in ("bundle", "item"):
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT,
                f"granularity 须为 'bundle' 或 'item': {granularity!r}",
            )
        if not approved:
            return await deps.plugins.unapprove(name, _actor)
        if granularity == "bundle":
            return await deps.plugins.approve(name, _actor)
        return await deps.plugins.approve_item(
            name, _actor, skills=skills, hooks=hooks, mcp=mcp
        )
