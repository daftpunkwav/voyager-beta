"""设置 service 单元测试"""
from api_backend.models.app_state import AppState
from api_backend.services.settings_service import settings_to_out


def test_settings_to_out_defaults():
    state = AppState(id=1, display_name="u", settings_json="{}")
    out = settings_to_out(state)
    assert out.theme in ("dark", "light")
    assert out.llm_configured is False
    assert isinstance(out.agent_llm_configs, list)
    assert len(out.agent_llm_configs) == 7
    assert out.agent_code_of_conduct == ""
    assert len(out.agent_guidelines) == 7
    assert all(g.guideline == "" for g in out.agent_guidelines)
