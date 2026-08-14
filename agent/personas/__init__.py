"""人格预设(纯数据,§9.3):Lucien 常驻;Iris/Elio/Miyai/Atlas 为派遣预设。"""

from agent.personas.atlas import ATLAS
from agent.personas.base import Persona
from agent.personas.elio import ELIO
from agent.personas.iris import IRIS
from agent.personas.lucien import LUCIEN
from agent.personas.miyai import MIYAI

PERSONAS: dict[str, Persona] = {p.key: p for p in (LUCIEN, IRIS, ELIO, MIYAI, ATLAS)}

__all__ = ["ATLAS", "ELIO", "IRIS", "LUCIEN", "MIYAI", "PERSONAS", "Persona"]
