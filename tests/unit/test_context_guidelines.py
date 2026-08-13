"""ContextBuilder 行为准则注入单测"""
from types import SimpleNamespace
from uuid import uuid4

from agent_core.memory.context import AgentRunContext, ContextBuilder


def test_build_system_prompt_injects_guidelines():
    builder = ContextBuilder(db=None, memory=None)  # type: ignore[arg-type]
    agent_def = SimpleNamespace(
        system_prompt="你是测试 Agent。",
        soul={"core": "核心人格", "default": "默认风格"},
    )
    ctx = AgentRunContext(
        session_id=uuid4(),
        agent_id="hub",
        db=None,  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        llm_config=None,
        memory=None,  # type: ignore[arg-type]
        code_of_conduct="回答务必简洁",
        agent_guideline="优先调度 Mentor",
    )
    prompt = builder.build_system_prompt(agent_def, ctx)
    assert "## 用户行为准则（必须遵守）" in prompt
    assert "回答务必简洁" in prompt
    assert "## 本 Agent 专属准则" in prompt
    assert "优先调度 Mentor" in prompt


def test_build_system_prompt_points_to_get_learner_info():
    builder = ContextBuilder(db=None, memory=None)  # type: ignore[arg-type]
    agent_def = SimpleNamespace(
        system_prompt="你是测试 Agent。",
        soul={"core": "核心人格", "default": "默认风格"},
    )
    ctx = AgentRunContext(
        session_id=uuid4(),
        agent_id="hub",
        db=None,  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        llm_config=None,
        memory=None,  # type: ignore[arg-type]
        user_profile={
            "identity": {"preferred_name": "阿城"},
            "tech_proficiency": {"Python": {"level": "advanced"}},
        },
    )
    prompt = builder.build_system_prompt(agent_def, ctx)
    assert "## 学习者信息" in prompt
    assert "get_learner_info" in prompt
    assert "阿城" in prompt
    # 默认不注入完整熟练度明细
    assert '"level": "advanced"' not in prompt
    assert "技术熟练度:" not in prompt


def test_build_system_prompt_skips_empty_guidelines():
    builder = ContextBuilder(db=None, memory=None)  # type: ignore[arg-type]
    agent_def = SimpleNamespace(
        system_prompt="你是测试 Agent。",
        soul={"core": "核心人格", "default": "默认风格"},
    )
    ctx = AgentRunContext(
        session_id=uuid4(),
        agent_id="hub",
        db=None,  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        llm_config=None,
        memory=None,  # type: ignore[arg-type]
    )
    prompt = builder.build_system_prompt(agent_def, ctx)
    assert "用户行为准则" not in prompt
    assert "本 Agent 专属准则" not in prompt
