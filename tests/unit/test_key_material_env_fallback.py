"""agent_core _key_material() 密钥同源回归测试。

钉住 B-1 修复：环境变量为空时，_key_material() 应回退到仓库根 .env，
与 api_backend Settings.secret_key 同源；且进程级缓存（不热重载）。
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """每个测试隔离环境变量与 lru_cache。"""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
    from agent_core.llm.config import _key_material

    _key_material.cache_clear()
    yield
    _key_material.cache_clear()


def test_key_material_falls_back_to_env_file(monkeypatch):
    """环境变量未设时，从仓库根 .env 读取，与 Settings.secret_key 同源。"""
    from agent_core.llm.config import _key_material
    from api_backend.config import get_settings

    get_settings.cache_clear()
    material = _key_material()
    assert material, "环境变量为空时 _key_material() 不应返回空串"
    assert material == get_settings().secret_key, "agent 密钥材料应与 api_backend Settings 同源"


def test_key_material_env_var_takes_precedence(monkeypatch):
    """环境变量优先于 .env 文件。"""
    monkeypatch.setenv("SECRET_KEY", "env-secret-at-least-32-bytes-long!!!")
    from agent_core.llm.config import _key_material

    assert _key_material() == "env-secret-at-least-32-bytes-long!!!"


def test_key_material_encryption_key_preferred(monkeypatch):
    """SECRETS_ENCRYPTION_KEY 优先于 SECRET_KEY。"""
    monkeypatch.setenv("SECRET_KEY", "fallback-secret-at-least-32-bytes-long!!")
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "dedicated-enc-key-32bytes-min!")
    from agent_core.llm.config import _key_material

    assert _key_material() == "dedicated-enc-key-32bytes-min!"


def test_key_material_is_cached(monkeypatch):
    """lru_cache 确保进程启动后 .env 篡改不影响已加载的密钥。"""
    from agent_core.llm.config import _key_material

    first = _key_material()
    # 模拟 .env 被篡改：改环境变量不影响已缓存的值
    monkeypatch.setenv("SECRET_KEY", "attacker-key-at-least-32-bytes-long!!")
    assert _key_material() == first, "已缓存的密钥材料不应受运行时环境变量变更影响"
