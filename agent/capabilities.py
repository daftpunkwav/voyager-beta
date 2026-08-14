"""agent 自己暴露的能力(§5 capabilities.py):经 gateway 与用户同权(铁律 4 parity)。

用户能在设置页做的,agent 也能做——除 secret(api key 等),由 settings 框架层拒绝。
handler 声明 `_actor` 参数时,框架注入调用者 ActorRef(见 platform_capability.guards)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ActorRef

from agent.context.pages import PageContextRegistry
from agent.memory import Memory
from agent.skills.loader import SkillLoader
from agent.subagent.registry import SubagentRegistry
from agent.subagent.spawn import Spawner
from agent.tools.ask_user import AskUser


@dataclass
class CapabilityDeps:
    settings: Any  # SettingsStore
    memory: Memory
    skills: SkillLoader
    spawner: Spawner
    subagents: SubagentRegistry
    pages: PageContextRegistry
    asker: AskUser


def build_agent_registry(deps: CapabilityDeps) -> Registry:
    reg = Registry("agent")

    @capability(reg, name="get_settings", description="列出全部设置项 schema(secret 只回 has_value)")
    def get_settings() -> list[dict]:
        return deps.settings.list_schema()

    @capability(reg, name="set_setting", description="修改一个设置项(secret 项会被框架拒绝)")
    async def set_setting(key: str, value, _actor: ActorRef = None) -> dict:
        await deps.settings.set(key, value, _actor)
        return {"key": key, "ok": True}

    @capability(reg, name="list_skills", description="skill 索引(常驻:name + 描述)")
    def list_skills() -> list[dict]:
        return deps.skills.index()

    @capability(reg, name="read_skill", description="按需读 skill 全文")
    def read_skill(name: str) -> dict:
        return {"name": name, "text": deps.skills.full_text(name)}

    @capability(reg, name="list_subagents", description="已注册的 subagent 定义 + 运行中实例")
    def list_subagents() -> dict:
        return {
            "definitions": [
                {"name": d.name, "mode": d.mode, "description": d.description}
                for d in deps.subagents.list()
            ],
            "running": [
                {"id": i.id, "name": i.name, "status": i.status.value, "goal": i.task.goal}
                for i in deps.spawner.instances.values()
            ],
        }

    @capability(reg, name="recall_memory", description="检索 agent 记忆(画像/情节/语义)")
    def recall_memory(query: str, limit: int = 8) -> list[dict]:
        return deps.memory.recall(query, limit)

    @capability(reg, name="report_page_context", description="页面上报:前端 provider 推送页面摘要(§10.12)")
    def report_page_context(
        page: str, summary: str, counts: dict | None = None, selected: str = ""
    ) -> dict:
        item = deps.pages.update(page, summary, counts=counts, selected=selected)
        return {"page": item.page, "ok": True}

    @capability(reg, name="answer_question", description="AskUser 答案回投(§9.15)")
    def answer_question(question_id: str, value) -> dict:
        return {"matched": deps.asker.answer(question_id, value)}

    return reg
