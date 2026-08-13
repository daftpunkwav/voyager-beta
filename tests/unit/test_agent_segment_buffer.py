"""按 Agent 分段缓冲落库辅助逻辑"""
import pytest
from agent_runtime.execution import _AgentSegmentBuffer


@pytest.mark.asyncio
async def test_segment_buffer_switch_flushes(monkeypatch):
    flushed: list[tuple[str, str, dict | None]] = []

    async def fake_append(db, session, *, role, content, agent_id=None, metadata=None, **kw):
        flushed.append((agent_id or "?", content, metadata))
        return None

    monkeypatch.setattr(
        "agent_runtime.execution.append_message",
        fake_append,
    )

    buf = _AgentSegmentBuffer(agent_id="hub")
    buf.append_delta("hub 前言")
    await buf.switch_agent(None, type("S", (), {"active_agent": "hub"})(), "mentor")
    buf.append_delta("mentor 正文")
    await buf.flush(None, type("S", (), {"active_agent": "mentor"})())

    assert [(a, c) for a, c, _ in flushed] == [
        ("hub", "hub 前言"),
        ("mentor", "mentor 正文"),
    ]


@pytest.mark.asyncio
async def test_segment_buffer_persists_thinking_on_switch(monkeypatch):
    flushed: list[tuple[str, str, dict | None]] = []

    async def fake_append(db, session, *, role, content, agent_id=None, metadata=None, **kw):
        flushed.append((agent_id or "?", content, metadata))
        return None

    monkeypatch.setattr(
        "agent_runtime.execution.append_message",
        fake_append,
    )

    session = type("S", (), {"active_agent": "hub"})()
    buf = _AgentSegmentBuffer(agent_id="hub")
    buf.append_thinking("[状态] Hub · 调度中\n")
    buf.append_delta("正在调度专业 Agent 处理…")
    await buf.switch_agent(None, session, "scout")

    buf.append_thinking("[执行] Scout · 第 1/2 轮\n分析 openai/codex 架构…\n")
    buf.append_delta("下面以系统级 Rust 视角梳理…")
    await buf.switch_agent(None, session, "hub")

    assert len(flushed) == 2
    hub_agent, hub_content, hub_meta = flushed[0]
    scout_agent, scout_content, scout_meta = flushed[1]
    assert hub_agent == "hub"
    assert hub_content == "正在调度专业 Agent 处理…"
    assert hub_meta and "调度中" in (hub_meta.get("thinking") or "")
    assert scout_agent == "scout"
    assert "Rust" in scout_content
    assert scout_meta and "分析 openai/codex" in (scout_meta.get("thinking") or "")
