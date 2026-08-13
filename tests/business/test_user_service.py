"""app_state_to_out 单元测试。"""
from datetime import datetime

from api_backend.models.app_state import AppState
from api_backend.services.user_service import app_state_to_out


def test_app_state_to_out_github_bound_false():
    state = AppState(
        id=1,
        display_name="local",
        github_accounts="[]",
        created_at=datetime.utcnow(),
    )
    out = app_state_to_out(state)
    assert out.github_bound is False
    assert out.github_login is None
    assert out.username == "local"
    assert out.id == "local"


def test_app_state_to_out_github_bound_true():
    state = AppState(
        id=1,
        display_name="local",
        github_accounts='[{"username": "octocat", "token": "x"}]',
        created_at=datetime.utcnow(),
    )
    out = app_state_to_out(state)
    assert out.github_bound is True
    assert out.github_login == "octocat"
