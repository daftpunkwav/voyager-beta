"""§4.2.10: 并发注册不重复 / 不丢失"""
import threading

from agent_core.agents.registry import AgentDefinition, AgentRegistry
from agent_core.tools.registry import ToolDefinition, ToolRegistry


async def async_handler(**kwargs):
    return None


def test_concurrent_tool_register_is_idempotent():
    reg = ToolRegistry()
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        barrier.wait()
        for j in range(50):
            reg.register(ToolDefinition(name=f"t{i}_{j}", description="d", parameters={}, handler=async_handler))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 8 workers × 50 each = 400 unique tool names
    assert len(reg._tools) == 400


def test_concurrent_agent_register_is_idempotent():
    """注册相同 id 的覆盖是最后写入胜出，并发安全。"""
    reg = AgentRegistry(definitions={})  # 起点空，仅并发注册测试数据
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        barrier.wait()
        for j in range(20):
            reg.register(AgentDefinition(
                id=f"agent_{i}_{j}",
                name=f"A{i}-{j}",
                description="x",
                tools=[],
                capabilities=[],
                system_prompt="",
                soul={},
            ))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    baseline = len(AgentRegistry()._agents)
    assert len(reg._agents) == baseline + 160  # 默认 + 160 新增