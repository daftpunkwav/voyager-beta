"""笔记批量动作:archive/unarchive/delete/export/pin/unpin。单篇失败不中断。"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .lifecycle import delete_note, update_note
from .runtime import DOMAIN, registry, require_alive
from .transfer import export_markdown

_BATCH_ACTIONS = ("archive", "unarchive", "delete", "export", "pin", "unpin")
_BATCH_MAX = 100


def _unique_ids(ids: object) -> list[str]:
    if isinstance(ids, str) or not isinstance(ids, (list, tuple)):
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "ids 须为字符串列表")
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        nid = str(raw or "").strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        out.append(nid)
    return out


@capability(registry, name="batch_notes",
            description="对多篇笔记做同一动作:archive|unarchive|delete|export|pin|unpin。"
                        "ids 最多 100,单篇失败记入 failed 不中断其余。"
                        "用户与 agent 调本能力等价。",
            cost=2, reversible=True)
async def batch_notes(ids: list[str], action: str) -> dict:
    action = (action or "").strip()
    if action not in _BATCH_ACTIONS:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"action 须为 {list(_BATCH_ACTIONS)}")
    nids = _unique_ids(ids)
    if not nids:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "ids 不能为空")
    if len(nids) > _BATCH_MAX:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"一次最多 {_BATCH_MAX} 篇")
    ok: list[str] = []
    failed: list[dict] = []
    paths: list[str] = []
    for nid in nids:
        try:
            if action == "archive":
                await update_note(nid, archived=True)
            elif action == "unarchive":
                await update_note(nid, archived=False)
            elif action == "pin":
                await update_note(nid, pinned=True)
            elif action == "unpin":
                await update_note(nid, pinned=False)
            elif action == "delete":
                await delete_note(nid)
            else:
                exported = export_markdown(require_alive(nid))
                paths.append(exported["path"])
            ok.append(nid)
        except ServiceError as exc:
            failed.append({"id": nid, "error": exc.body.message})
    result: dict = {"ok": ok, "failed": failed, "action": action, "count": len(ok)}
    if paths:
        result["paths"] = paths
    return result
