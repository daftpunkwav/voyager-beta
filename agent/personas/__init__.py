"""人格预设(纯数据,§9.3):结构 ID 按职责;显示名留在 Persona.display_name。

旧 key(lucien/iris/hub/scout/…)经 ALIASES 解析到职责 ID,持久化会话可迁移。
"""

from agent.personas.base import Persona
from agent.personas.explainer import EXPLAINER
from agent.personas.graph_guide import GRAPH_GUIDE
from agent.personas.orchestrator import ORCHESTRATOR
from agent.personas.organizer import ORGANIZER
from agent.personas.recon import RECON

# 显示名常量别名(测试与旧 import);结构 ID 以 .key 为准
LUCIEN = ORCHESTRATOR
IRIS = RECON
ELIO = EXPLAINER
MIYAI = ORGANIZER
ATLAS = GRAPH_GUIDE

PERSONAS: dict[str, Persona] = {
    p.key: p for p in (ORCHESTRATOR, RECON, EXPLAINER, ORGANIZER, GRAPH_GUIDE)
}

#: 旧结构 ID / 前端七角色 → 职责 ID
ALIASES: dict[str, str] = {
    "lucien": "orchestrator",
    "hub": "orchestrator",
    "iris": "recon",
    "scout": "recon",
    "navigator": "recon",
    "elio": "explainer",
    "mentor": "explainer",
    "miyai": "organizer",
    "curator": "organizer",
    "scribe": "organizer",
    "atlas": "graph_guide",
}


def canonical_persona_key(key: str) -> str:
    """把别名收成职责 ID;未知 key 原样返回(自建 subagent 名)。"""
    return ALIASES.get(key, key)


def resolve_persona(key: str) -> Persona | None:
    """按职责 ID 或历史别名取内置人格;未命中返回 None。"""
    if not key:
        return None
    return PERSONAS.get(canonical_persona_key(key))


__all__ = [
    "ALIASES",
    "ATLAS",
    "ELIO",
    "EXPLAINER",
    "GRAPH_GUIDE",
    "IRIS",
    "LUCIEN",
    "MIYAI",
    "ORCHESTRATOR",
    "ORGANIZER",
    "PERSONAS",
    "Persona",
    "RECON",
    "canonical_persona_key",
    "resolve_persona",
]
