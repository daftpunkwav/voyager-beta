"""AskUser 答案回投能力。"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="answer_question", description="AskUser 答案回投(§9.15)")
    def answer_question(question_id: str, value) -> dict:
        return {"matched": deps.asker.answer(question_id, value)}
