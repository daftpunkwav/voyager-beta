"""Hub 寒暄快路径：跳过 plan_execute，禁止复述编排规范"""
from agent_core.agents.hub import apply_chitchat_mode, is_simple_chitchat
from agent_core.agents.registry import AGENT_DEFINITIONS


def test_is_simple_chitchat_positive():
    for msg in ("你好", "您好！", "hi", "Hello", "嗨", "早上好", "在吗？"):
        assert is_simple_chitchat(msg), msg


def test_is_simple_chitchat_negative():
    for msg in (
        "你好，帮我分析这个仓库",
        "想学习 langchain",
        "帮我规划路线",
        "",
        "a" * 30,
    ):
        assert not is_simple_chitchat(msg), msg


def test_apply_chitchat_mode_forces_direct_no_tools():
    hub = AGENT_DEFINITIONS["hub"]
    assert hub.workflow == "plan_execute"
    assert "dispatch_agent" in hub.tools
    mode = apply_chitchat_mode(hub)
    assert mode.workflow == "direct"
    assert mode.tools == []
    assert mode.max_iterations == 1
    assert mode.max_tokens <= 320
    prompt = mode.system_prompt or ""
    assert "严禁" in prompt
    assert "dispatch_agent" in prompt  # 作为禁止提及的反例
    assert "按以下规则执行" in prompt
    # 原定义不被就地修改
    assert hub.workflow == "plan_execute"
    assert "dispatch_agent" in hub.tools
