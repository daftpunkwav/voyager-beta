"""bridge 测试:注册表 → AgentTool 的名称、元数据、守卫链调用与 trace 贯穿。"""

import asyncio

from platform_capability import Registry, SqliteAuditSink, capability

from agent.runtime.trace import reset_current_trace, set_current_trace
from deploy.bridge import make_domain_tools
from services.gateway.mounts import MountSpec


def _echo_mounts():
    reg = Registry("echo")

    @capability(reg, name="ping", description="回声测试", cost=2, reversible=False)
    async def ping(text: str = "") -> dict:
        return {"pong": text}

    return [MountSpec(domain="echo", registry=reg, probe=None)]


def test_names_and_metadata() -> None:
    tools = make_domain_tools(_echo_mounts())
    assert list(tools) == ["echo__ping"]
    tool = tools["echo__ping"]
    assert tool.name == "echo__ping"
    assert tool.description == "[echo] 回声测试"
    assert tool.dimension == "app"  # 领域能力统一 app 维
    assert tool.write is True  # write 默认 True(不显式声明时与旧 cost>0 档一致)
    assert tool.irreversible is True  # reversible=False 透传


def test_write_is_explicit_not_cost_derived() -> None:
    """write 与 cost 解耦(phase-14):显式声明原样透传,禁止再从 cost 推导。"""
    reg = Registry("w")

    @capability(reg, name="read_only", description="零 cost 但声明为写",
                cost=0, write=True)
    async def read_only() -> dict:
        return {}

    @capability(reg, name="expensive_read", description="高 cost 但只读",
                cost=5, write=False)
    async def expensive_read() -> dict:
        return {}

    tools = make_domain_tools([MountSpec(domain="w", registry=reg, probe=None)])
    assert tools["w__read_only"].write is True  # cost=0, write=True
    assert tools["w__expensive_read"].write is False  # cost=5, write=False


def test_handler_calls_through_capability_framework() -> None:
    tools = make_domain_tools(_echo_mounts())
    out = asyncio.run(tools["echo__ping"].handler(text="hi"))
    assert out == {"pong": "hi"}


def test_multiple_mounts_no_name_collision() -> None:
    reg_a = Registry("a")
    reg_b = Registry("b")
    capability(reg_a, name="same", description="a")(lambda: {"from": "a"})
    capability(reg_b, name="same", description="b")(lambda: {"from": "b"})
    tools = make_domain_tools([
        MountSpec(domain="a", registry=reg_a, probe=None),
        MountSpec(domain="b", registry=reg_b, probe=None),
    ])
    assert set(tools) == {"a__same", "b__same"}
    assert asyncio.run(tools["a__same"].handler()) == {"from": "a"}
    assert asyncio.run(tools["b__same"].handler()) == {"from": "b"}


def test_handler_carries_current_trace(tmp_path) -> None:
    """链上设置了 trace 时,agent 的能力调用沿用同一 trace(审计整链回放,§7.8)。"""
    sink = SqliteAuditSink(tmp_path / "audit.db")
    tools = make_domain_tools(_echo_mounts(), audit=[sink])
    token = set_current_trace("trace-from-user-message")
    try:
        out = asyncio.run(tools["echo__ping"].handler(text="hi"))
        assert out == {"pong": "hi"}
    finally:
        reset_current_trace(token)
    rows = sink.recent(trace_id="trace-from-user-message")
    assert len(rows) == 1 and rows[0]["capability"] == "ping"
    sink.close()
