"""学习者画像持久化 —— 单例 UserProfile（id=1）"""
import json

from api_backend.models.agent import LEARNER_PROFILE_ID, UserProfile
from api_backend.models.app_state import APP_STATE_ID, AppState
from api_backend.schemas.profile import (
    GoalOut,
    LearnerIdentityOut,
    LearnerIdentityUpdate,
    MemoryItemOut,
    MemoryProposalOut,
    UserProfileOut,
    UserProfileUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PROFILE = UserProfileOut()

# Agent get_learner_info 允许请求的字段
LEARNER_INFO_FIELDS = frozenset(
    {
        "preferred_name",
        "spoken_languages",
        "programming_languages",
        "tech_stack",
        "interests",
        "occupation",
        "experience_level",
        "bio",
        "learning_preferences",
        "tech_proficiency",
        "goals",
        "history_summary",
    }
)


def _parse_json(text: str | None, fallback):
    try:
        value = json.loads(text or "")
        return value if isinstance(value, (dict, list)) else fallback
    except json.JSONDecodeError:
        return fallback


def _identity_from_raw(raw: dict) -> LearnerIdentityOut:
    if not isinstance(raw, dict):
        return LearnerIdentityOut()
    try:
        return LearnerIdentityOut.model_validate(raw)
    except Exception:
        return LearnerIdentityOut()


def _merge_identity(
    current: LearnerIdentityOut, patch: LearnerIdentityUpdate
) -> LearnerIdentityOut:
    data = current.model_dump()
    for key, value in patch.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if isinstance(value, list):
            # 规范化：去空白、去重保序
            cleaned: list[str] = []
            seen: set[str] = set()
            for item in value:
                s = str(item).strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                cleaned.append(s[:64])
            data[key] = cleaned[:32]
        elif isinstance(value, str):
            data[key] = value.strip()
        else:
            data[key] = value
    return LearnerIdentityOut.model_validate(data)


def profile_to_out(row: UserProfile) -> UserProfileOut:
    memory_raw = _parse_json(row.agent_prefs, {})
    memory_items = memory_raw.get("memory_items", []) if isinstance(memory_raw, dict) else []
    extensions = memory_raw.get("extensions", {}) if isinstance(memory_raw, dict) else {}
    pending_raw = (
        memory_raw.get("pending_memory_proposals", [])
        if isinstance(memory_raw, dict)
        else []
    )
    goals = [GoalOut.model_validate(g) for g in _parse_json(row.goals, [])]
    memory: list[MemoryItemOut] = []
    for m in memory_items:
        if not isinstance(m, dict):
            continue
        try:
            normalized = {
                "id": m.get("id") or f"mem_{len(memory)}",
                "category": m.get("category") or "summary",
                "content": m.get("content") or m.get("value") or "",
                "created_at": m.get("created_at") or m.get("at") or "",
                "updated_at": m.get("updated_at"),
            }
            if not normalized["content"]:
                continue
            memory.append(MemoryItemOut.model_validate(normalized))
        except Exception:
            continue
    pending: list[MemoryProposalOut] = []
    for p in pending_raw if isinstance(pending_raw, list) else []:
        if not isinstance(p, dict):
            continue
        try:
            pending.append(
                MemoryProposalOut.model_validate(
                    {
                        "id": p.get("id") or f"prop_{len(pending)}",
                        "kind": p.get("kind") or "long_memory",
                        "value": str(p.get("value") or "")[:2000],
                        "confidence": float(p.get("confidence") or 0.7),
                        "agent_id": p.get("agent_id") or "hub",
                        "evidence": list(p.get("evidence") or [])[:8],
                        "at": p.get("at") or "",
                    }
                )
            )
        except Exception:
            continue
    identity = _identity_from_raw(_parse_json(row.identity_json, {}))
    return UserProfileOut(
        identity=identity,
        tech_proficiency=_parse_json(row.tech_profile, {}),
        learning_preferences=_parse_json(row.preferences, {}),
        goals=goals,
        history_summary=row.history_summary or "",
        memory_items=memory,
        pending_memory_proposals=pending,
        extensions=extensions if isinstance(extensions, dict) else {},
    )


async def get_or_create_profile(db: AsyncSession) -> UserProfile:
    row = await db.get(UserProfile, LEARNER_PROFILE_ID)
    if row:
        return row
    row = UserProfile(id=LEARNER_PROFILE_ID)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_user_profile(db: AsyncSession) -> UserProfileOut:
    row = await get_or_create_profile(db)
    return profile_to_out(row)


async def _sync_display_name(db: AsyncSession, preferred_name: str) -> None:
    """称呼变更时同步 AppState.display_name，供总览问候等使用。"""
    name = (preferred_name or "").strip() or "local"
    state = await db.get(AppState, APP_STATE_ID)
    if state is None:
        return
    if state.display_name != name:
        state.display_name = name[:64]


async def update_user_profile(
    db: AsyncSession, data: UserProfileUpdate
) -> UserProfileOut:
    row = await get_or_create_profile(db)
    if data.identity is not None:
        current = _identity_from_raw(_parse_json(row.identity_json, {}))
        merged = _merge_identity(current, data.identity)
        row.identity_json = json.dumps(merged.model_dump(), ensure_ascii=False)
        await _sync_display_name(db, merged.preferred_name)
    if data.tech_proficiency is not None:
        row.tech_profile = json.dumps(data.tech_proficiency, ensure_ascii=False)
    if data.learning_preferences is not None:
        row.preferences = json.dumps(data.learning_preferences, ensure_ascii=False)
    if data.goals is not None:
        row.goals = json.dumps([g.model_dump() for g in data.goals], ensure_ascii=False)
    if data.history_summary is not None:
        row.history_summary = data.history_summary
    if data.memory_items is not None or data.extensions is not None:
        prefs = _parse_json(row.agent_prefs, {})
        if not isinstance(prefs, dict):
            prefs = {}
        if data.memory_items is not None:
            prefs["memory_items"] = [m.model_dump() for m in data.memory_items]
        if data.extensions is not None:
            prefs["extensions"] = data.extensions
        row.agent_prefs = json.dumps(prefs, ensure_ascii=False)
    await db.commit()
    await db.refresh(row)
    return profile_to_out(row)


async def clear_user_memory(db: AsyncSession) -> UserProfileOut:
    """清除 Agent 推断的画像记忆；保留本机自填 identity。不删除对话会话。"""
    row = await get_or_create_profile(db)
    current = _parse_json(row.agent_prefs, {})
    if not isinstance(current, dict):
        current = {}
    extensions = current.get("extensions", {})
    if not isinstance(extensions, dict):
        extensions = {}
    row.tech_profile = "{}"
    row.preferences = "{}"
    row.goals = "[]"
    row.history_summary = ""
    row.agent_prefs = json.dumps(
        {
            "memory_items": [],
            "pending_memory_proposals": [],
            "short_memory": {},
            "extensions": extensions,
        },
        ensure_ascii=False,
    )
    await db.commit()
    await db.refresh(row)
    return profile_to_out(row)


def select_learner_info(profile: UserProfileOut, fields: list[str]) -> dict:
    """按字段白名单抽取学习者信息（供 Agent 工具使用）。"""
    full = {
        "preferred_name": profile.identity.preferred_name,
        "spoken_languages": profile.identity.spoken_languages,
        "programming_languages": profile.identity.programming_languages,
        "tech_stack": profile.identity.tech_stack,
        "interests": profile.identity.interests,
        "occupation": profile.identity.occupation,
        "experience_level": profile.identity.experience_level,
        "bio": profile.identity.bio,
        "learning_preferences": profile.learning_preferences,
        "tech_proficiency": profile.tech_proficiency,
        "goals": [g.model_dump() for g in profile.goals],
        "history_summary": profile.history_summary,
    }
    requested = [f for f in fields if f in LEARNER_INFO_FIELDS]
    unknown = [f for f in fields if f not in LEARNER_INFO_FIELDS]
    result = {k: full[k] for k in requested}
    if unknown:
        result["_unknown_fields"] = unknown
        result["_available_fields"] = sorted(LEARNER_INFO_FIELDS)
    return result
