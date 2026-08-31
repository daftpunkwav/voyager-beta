"""设置相关能力:列出 schema、修改设置项。"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorRef

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="get_settings", description="列出全部设置项 schema(secret 只回 has_value)")
    def get_settings() -> list[dict]:
        return deps.settings.list_schema()

    @capability(reg, name="set_setting", description="修改一个设置项(secret 项会被框架拒绝)")
    async def set_setting(key: str, value, _actor: ActorRef = None) -> dict:
        await deps.settings.set(key, value, _actor)
        return {"key": key, "ok": True}
