"""本机身份序列化 —— 从 AppState 派生 UserOut。"""
import json

from api_backend.models.app_state import AppState
from api_backend.schemas.user import UserOut

# 本机身份固定 id（字符串，非 UUID）
LOCAL_IDENTITY_ID = "local"


def app_state_to_out(state: AppState) -> UserOut:
    """ORM AppState → 前端 UserOut（本机身份）。"""
    github_accounts: list[dict] = []
    try:
        github_accounts = json.loads(state.github_accounts or "[]")
    except json.JSONDecodeError:
        github_accounts = []
    first = github_accounts[0] if github_accounts else None
    return UserOut(
        id=LOCAL_IDENTITY_ID,
        username=state.display_name or "local",
        github_login=first.get("username") if isinstance(first, dict) else None,
        github_bound=bool(github_accounts),
        created_at=state.created_at,
    )
