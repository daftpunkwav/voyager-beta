"""skill 索引与全文读取能力。"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_skills", description="skill 索引(常驻:name + 描述)")
    def list_skills() -> list[dict]:
        return deps.skills.index()

    @capability(reg, name="read_skill", description="按需读 skill 全文")
    def read_skill(name: str) -> dict:
        try:
            text = deps.skills.full_text(name)
        except KeyError:
            # loader 层抛 KeyError(单元测试锁定);capability 面翻译成 NOT_FOUND,
            # 不给调用方裸内部异常(未批准 / 已删除的 skill 都走这里)
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND, f"没有这个技能: {name}"
            ) from None
        return {"name": name, "text": text}
