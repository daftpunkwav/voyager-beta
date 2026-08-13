"""select_learner_info / 画像字段白名单"""
from api_backend.schemas.profile import LearnerIdentityOut, UserProfileOut
from api_backend.services.profile_service import select_learner_info


def test_select_learner_info_subset():
    profile = UserProfileOut(
        identity=LearnerIdentityOut(
            preferred_name="阿城",
            tech_stack=["React", "FastAPI"],
            spoken_languages=["中文"],
        ),
        history_summary="本周学了 Hooks",
    )
    out = select_learner_info(profile, ["preferred_name", "tech_stack"])
    assert out == {
        "preferred_name": "阿城",
        "tech_stack": ["React", "FastAPI"],
    }
    assert "history_summary" not in out


def test_select_learner_info_unknown_fields():
    profile = UserProfileOut()
    out = select_learner_info(profile, ["preferred_name", "hobby"])
    assert "preferred_name" in out
    assert out["_unknown_fields"] == ["hobby"]
    assert "tech_stack" in out["_available_fields"]
