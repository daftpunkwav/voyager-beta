"""历史明文密钥读路径 re-encrypt 迁移测试"""
import json

import pytest
from api_backend.core.security import ensure_encrypted_secret, is_encrypted_secret
from api_backend.models.app_state import AppState
from api_backend.services.settings_service import get_settings


def test_ensure_encrypted_secret_migrates_plaintext():
    plain = "sk-legacy-plain-key"
    stored, migrated = ensure_encrypted_secret(plain)
    assert migrated is True
    assert is_encrypted_secret(stored)
    again, migrated2 = ensure_encrypted_secret(stored)
    assert migrated2 is False
    assert again == stored


def test_ensure_encrypted_secret_empty():
    assert ensure_encrypted_secret(None) == (None, False)
    assert ensure_encrypted_secret("") == ("", False)


@pytest.mark.asyncio
async def test_get_settings_reencrypts_plain_llm_key(tmp_path, monkeypatch):
    import os

    from api_backend.config import get_settings as gs
    from api_backend.core.security import decrypt_secret
    from api_backend.database import get_session_factory, init_db, reset_database
    from api_backend.services.app_state_service import get_or_create_app_state

    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'migrate.db'}"
    os.environ.setdefault("SECRET_KEY", "pytest-secret-key-do-not-use-in-prod")
    gs.cache_clear()
    reset_database()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:  # type: AsyncSession
        state = await get_or_create_app_state(session)
        state.settings_json = json.dumps({"llm_api_key": "sk-plain-legacy-key"})
        await session.commit()
        await session.refresh(state)

        out = await get_settings(session)
        assert out.llm_configured is True

        await session.refresh(state)
        raw = json.loads(state.settings_json)
        assert is_encrypted_secret(raw.get("llm_api_key"))
        assert decrypt_secret(raw.get("llm_api_key")) == "sk-plain-legacy-key"


def test_github_migrate_plaintext_pats():
    from api_backend.core.security import decrypt_secret
    from api_backend.services.github_accounts import load_accounts, migrate_plaintext_pats

    state = AppState(
        id=1,
        display_name="gh",
        github_accounts=json.dumps(
            [{"id": "1", "username": "octocat", "pat": "ghp_plain_token_xyz"}]
        ),
    )
    assert migrate_plaintext_pats(state) is True
    accounts = load_accounts(state)
    assert is_encrypted_secret(accounts[0]["pat"])
    assert decrypt_secret(accounts[0]["pat"]) == "ghp_plain_token_xyz"
    assert migrate_plaintext_pats(state) is False
