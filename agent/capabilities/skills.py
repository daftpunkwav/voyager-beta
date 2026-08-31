"""skill 索引与全文读取能力。"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_skills", description="skill 索引(常驻:name + 描述)")
    def list_skills() -> list[dict]:
        return deps.skills.index()

    @capability(reg, name="read_skill", description="按需读 skill 全文")
    def read_skill(name: str) -> dict:
        return {"name": name, "text": deps.skills.full_text(name)}
