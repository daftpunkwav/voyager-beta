"""bridge 测试:注册表 → AgentTool 的名称、元数据与守卫链调用。"""

import asyncio

from platform_capability import Registry, capability

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
    assert tool.write is True  # cost>0 视为消耗性操作
    assert tool.irreversible is True  # reversible=False 透传


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
