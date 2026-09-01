"""记忆与用户画像相关能力:检索、快照、清空、写入/删除画像。"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="recall_memory", description="检索 agent 记忆(画像/情节/语义)")
    def recall_memory(query: str, limit: int = 8) -> list[dict]:
        return deps.memory.recall(query, limit)

    @capability(reg, name="get_memory", description="记忆快照:画像摘要+键值、最近情节/语义、工作记忆条数")
    def get_memory() -> dict:
        """设置页数据源(§10.11):读 retention_days 并惰性清超期情节与语义事实(与 notes 回收站同精神)。"""
        retention = int(deps.settings.get("agent.memory.retention_days") or 0)
        purged = deps.memory.purge(retention)
        episodic_recent = deps.memory.episodic.recent(limit=20)
        semantic_recent = deps.memory.semantic.query(limit=20)
        return {
            "profile": {
                "summary": deps.memory.profile.render(),
                "items": [
                    {"key": k, "value": v} for k, v in deps.memory.profile.all().items()
                ],
            },
            "episodic": {"recent": episodic_recent, "shown": len(episodic_recent)},
            "semantic": {"recent": semantic_recent, "shown": len(semantic_recent)},
            "working": {"size": len(deps.memory.working)},
            "retention_days": retention,
            "purged_episodic": purged["episodic"],
            "purged_semantic": purged.get("semantic", 0),
        }

    @capability(reg, name="clear_memory", description="清空记忆区(zone: profile/episodic/semantic/working/all)",
                cost=2)
    def clear_memory(zone: str) -> dict:
        return {"zone": zone, "cleared": deps.memory.clear(zone)}

    @capability(reg, name="set_profile", description="写入/更新一条用户画像键值")
    def set_profile(key: str, value: str) -> dict:
        cleaned = (key or "").strip()
        if not cleaned:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "画像键不能为空")
        deps.memory.profile.set(cleaned, value)
        return {"key": cleaned, "ok": True}

    @capability(reg, name="delete_profile", description="删除一条用户画像键值(键不存在不报错)")
    def delete_profile(key: str) -> dict:
        cleaned = (key or "").strip()
        if not cleaned:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "画像键不能为空")
        deps.memory.profile.delete(cleaned)
        return {"key": cleaned, "ok": True}
