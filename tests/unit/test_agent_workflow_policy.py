"""Agent 工作流策略：速度档位与流式路径"""
from agent_core.agents.react import ReActEngine
from agent_core.agents.registry import AGENT_DEFINITIONS, GLOBAL_OUTPUT_RULES, render_soul


def test_scout_is_react_fast_lane():
    scout = AGENT_DEFINITIONS["scout"]
    assert scout.workflow == "react"
    assert scout.max_iterations <= 2
    assert scout.max_tokens <= 2400
    # 工具应极少，避免 ReAct 多轮
    assert len(scout.tools) <= 3
    assert "fetch_github_repo" in scout.tools
    assert "fetch_readme" in scout.tools
    assert "get_project_detail" in scout.tools
    assert "full_name=owner/repo" in scout.system_prompt
    assert "禁止把 owner/repo 当作 project_id" in scout.system_prompt


def test_hub_routes_external_github_without_fake_project_id():
    hub = AGENT_DEFINITIONS["hub"]
    assert "full_name=owner/repo" in hub.system_prompt
    assert "严禁把 owner/repo 当作 project_id" in hub.system_prompt


def test_mentor_react_bounded_iterations():
    mentor = AGENT_DEFINITIONS["mentor"]
    assert mentor.workflow == "react"
    assert mentor.max_iterations <= 2
    assert "manage_session_projects" not in mentor.tools


def test_no_emoji_rule_in_soul():
    text = render_soul(AGENT_DEFINITIONS["scout"].soul, "default")
    assert "emoji" in text.lower() or "表情" in text
    assert "禁止" in GLOBAL_OUTPUT_RULES


def test_prefer_token_stream_for_no_tools():
    engine = ReActEngine()
    scout = AGENT_DEFINITIONS["scout"]
    assert engine._prefer_token_stream(scout, tools=[]) is True
    # 有工具的 react 默认不走入口真流式（工具轮非流式）
    hub = AGENT_DEFINITIONS["hub"]
    assert engine._prefer_token_stream(hub, tools=[{"type": "function"}]) is False
    # direct 始终流式
    assert engine._prefer_token_stream(hub, tools=[]) is True


def test_effective_max_iter_uses_agent_def():
    engine = ReActEngine(max_iterations=8)
    scout = AGENT_DEFINITIONS["scout"]
    assert engine._effective_max_iter(scout) == 2


def test_llm_config_status_missing_and_ok():
    from agent_core.llm.config import llm_config_status

    assert llm_config_status({}) == "missing"
    assert llm_config_status({"llm_api_key": "sk-plain"}) == "ok"
