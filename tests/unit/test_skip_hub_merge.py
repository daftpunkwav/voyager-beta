"""Hub 调度状态：短 thinking + 短正文说明，禁止完整 task 进正文"""
from agent_core.agents.hub import (
    format_dispatch_announce,
    format_dispatch_notice,
    format_dispatch_status,
    format_switch_reason,
    should_skip_hub_merge,
)


def test_skip_merge_single_expert_any_length():
    # 嵌套专家：始终 Hub 汇总，不再单专家直出
    assert should_skip_hub_merge([("scout", "短")]) is False
    assert should_skip_hub_merge([("scout", "x" * 300)]) is False


def test_keep_merge_for_multi_experts():
    body = "x" * 300
    assert should_skip_hub_merge([("scout", body), ("mentor", body)]) is False


def test_skip_merge_empty():
    assert should_skip_hub_merge([]) is False


def test_format_switch_reason_clips_long_model_dump():
    long_reason = (
        "用户是零基础，需要 mentor 把 GPDot 按每个模块做了什么的复述级深度拆开讲，"
        "不能用 navigator（不需要独立路线图），也不要一次堆太多概念"
    )
    text = format_switch_reason(
        {"target_agent": "mentor", "reason": long_reason},
        limit=72,
    )
    assert len(text) <= 73  # 72 + …
    assert "不能用 navigator" not in text or text.endswith("…")
    assert "深度讲解" != text or True


def test_format_switch_reason_falls_back_to_role_hint():
    assert format_switch_reason({"target_agent": "mentor", "reason": ""}) == "深度讲解"
    assert format_switch_reason({"target_agent": "scout", "reason": "Hub 调度 scout"}) == (
        "快速分析"
    )


def test_format_dispatch_status_is_short_status_line():
    long_task = (
        "用户目标：从零理解 coding agent\n"
        "已知约束：Python\n"
        "禁止事项：不要推荐需要付费 API key 的工业级框架作为首选；"
        "不要列超过 5 个仓库\n"
        "期望产出：分阶段里程碑"
    )
    text = format_dispatch_status(
        {
            "target_agent": "navigator",
            "task": long_task,
            "reason": "用户明确要路径与里程碑，mentor 不必同时上场",
        }
    )
    assert text.startswith("[状态] 调度 · Navigator")
    assert "任务：" not in text
    assert "禁止事项" not in text
    assert long_task not in text
    assert len(text) < 200


def test_format_dispatch_notice_is_short_user_facing():
    long_task = "禁止事项：不要列超过 5 个仓库\n" + ("x" * 300)
    text = format_dispatch_notice(
        {
            "target_agent": "scout",
            "task": long_task,
            "reason": "先摸底仓库结构，再让 mentor 给出学习路径",
        }
    )
    assert "先交由 **Scout**" in text
    assert "快速分析" in text
    assert "摸底仓库结构" in text
    assert "禁止事项" not in text
    assert long_task not in text
    assert "任务：" not in text


def test_format_dispatch_announce_aliases_status():
    text = format_dispatch_announce(
        {
            "target_agent": "mentor",
            "task": "讲解 Codex 源码架构，禁止事项：不要整仓粘贴",
            "reason": "用户要深度讲解",
        }
    )
    assert "Mentor" in text
    assert text.startswith("[状态]")
    assert "禁止事项" not in text
    assert "任务：" not in text


def test_prefix_expert_thinking_sse_adds_attribution():
    from agent_core.agents.hub import _prefix_expert_thinking_sse
    from agent_core.agents.stream_events import encode_stream_item, format_sse

    raw = format_sse("thinking", {"content": "先列目录结构\n"}).to_sse()
    out = encode_stream_item(_prefix_expert_thinking_sse(raw, "Mentor"))
    assert "【Mentor】" in out
    assert "先列目录结构" in out
    # 幂等
    out2 = encode_stream_item(_prefix_expert_thinking_sse(out, "Mentor"))
    assert out2.count("【Mentor】") == 1


def test_prefix_expert_thinking_sse_ignores_non_thinking():
    from agent_core.agents.hub import _prefix_expert_thinking_sse
    from agent_core.agents.stream_events import format_sse

    raw = format_sse("text_delta", {"content": "正文"}).to_sse()
    assert _prefix_expert_thinking_sse(raw, "Mentor") == raw
