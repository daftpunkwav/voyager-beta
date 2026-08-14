"""skill 体系:索引常驻 + 全文按需(loader),重复流程自动整理(organizer)。"""

from agent.skills.loader import SkillLoader
from agent.skills.organizer import SkillOrganizer

__all__ = ["SkillLoader", "SkillOrganizer"]
