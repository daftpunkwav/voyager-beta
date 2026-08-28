"""笔记目录面:标签、反链、计数。"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .runtime import DOMAIN, get_any, registry, require_deps
from .validate import validate_tag


@capability(registry, name="list_tags", description="存活笔记的标签清单(含计数)")
def list_tags() -> list[dict]:
    return [{"tag": t, "count": c} for t, c in require_deps().store.all_tags()]


@capability(registry, name="rename_tag", description="全局重命名标签(所有笔记生效)", cost=2)
async def rename_tag(old: str, new: str) -> dict:
    old = validate_tag(old)
    new = validate_tag(new)
    if old == new:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "新旧标签相同")
    count = require_deps().store.rename_tag(old, new)
    return {"renamed_from": old, "to": new, "affected": count}


@capability(registry, name="get_backlinks", description="反链:哪些存活笔记链接到该笔记")
def get_backlinks(note_id: str) -> dict:
    get_any(note_id)
    links = require_deps().store.backlinks(note_id)
    return {"note_id": note_id, "backlinks": links}


@capability(registry, name="notes_stats", description="计数统计(活跃/归档/回收站/热门标签)")
def notes_stats() -> dict:
    return require_deps().store.stats()
