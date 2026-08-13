"""agent_services_bridge 契约完整性回归测试。

钉住 B1 修复：ProfileServicePort 必须携带 LEARNER_INFO_FIELDS，
否则 agent_core get_learner_info 空字段路径 AttributeError。
"""
from api_backend.services.agent_services_bridge import build_agent_services


def test_profile_contract_carries_learner_info_fields():
    svc = build_agent_services()
    profile = svc.profile
    assert hasattr(profile, "LEARNER_INFO_FIELDS"), "Profile 契约必须暴露 LEARNER_INFO_FIELDS"
    assert isinstance(profile.LEARNER_INFO_FIELDS, frozenset)
    assert "preferred_name" in profile.LEARNER_INFO_FIELDS


def test_build_agent_services_full_contract():
    """6 个契约服务全部注入且方法齐全。"""
    svc = build_agent_services()
    assert all(
        getattr(svc, name) is not None
        for name in (
            "app_state",
            "profile",
            "settings",
            "github",
            "llm_usage",
            "session_query",
        )
    )
    # 抽查方法签名与契约一致
    assert callable(svc.app_state.get_or_create_app_state)
    assert callable(svc.profile.profile_to_out)
    assert callable(svc.profile.get_user_profile)
    assert callable(svc.profile.select_learner_info)
    assert callable(svc.settings.ensure_providers)
    assert callable(svc.github.fetch_repo_info)
    assert callable(svc.github.fetch_readme_text)
    assert callable(svc.llm_usage.parse_usage_details)
    assert callable(svc.llm_usage.record_parsed_usage_fire_and_forget)
    assert callable(svc.session_query.get_session_project_ids)
