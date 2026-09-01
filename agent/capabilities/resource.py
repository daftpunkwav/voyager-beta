"""资源配额能力(§9.9 资源维):当日 token 用量与配额上限,只读。"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="get_resource_quota", description="当日 token 用量与配额上限(§9.9)")
    def get_resource_quota() -> dict:
        """返回当日已用 token 与日配额上限。

        - tokens_used_today:与 Meter.tokens_used_today 同语义,UTC 自然日切日,
          input+output 合计;
        - daily_tokens:热读 agent.resource.daily_tokens,0 = 不限;
        - 不派生百分比/是否超限,展示口径留给前端。
        """
        limit = int(deps.settings.get("agent.resource.daily_tokens") or 0)
        used = deps.meter.tokens_used_today()
        return {"tokens_used_today": used, "daily_tokens": limit}
