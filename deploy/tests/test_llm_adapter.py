"""ServiceLLM 测试:complete 能力结果 → LLMReply 映射与降级路径。"""

from platform_contracts import ErrorSuffix, ServiceError

from agent.llm import ToolSpec
from deploy.llm_adapter import ServiceLLM

MSGS = [{"role": "user", "content": "hi"}]
TOOLS = [ToolSpec(name="t", description="d", schema={"type": "object"})]


def _call_with_provider(reply: dict, calls: list):
    async def call(domain: str, name: str, args: dict) -> dict:
        calls.append((domain, name, args))
        if name == "list_providers":
            return [{"id": "p1", "enabled": True, "has_api_key": True,
                     "default_model": "m9"}]
        return reply

    return call


class TestMapping:
    async def test_reply_with_tool_calls(self) -> None:
        calls: list = []
        llm = ServiceLLM(_call_with_provider({
            "text": "", "model": "m9",
            "tool_calls": [{"id": "c1", "name": "t", "arguments": {"a": 1}}],
            "usage": {"input_tokens": 2, "output_tokens": 3},
        }, calls))
        reply = await llm.complete(MSGS, tools=TOOLS)
        assert reply.final is False
        assert reply.tool_calls[0].id == "c1"
        assert reply.tool_calls[0].arguments == {"a": 1}
        assert (reply.usage.input_tokens, reply.usage.output_tokens) == (2, 3)
        # complete 调用参数:自动选择第一个可用提供商,tools 转 dict 形态
        domain, name, args = calls[-1]
        assert (domain, name) == ("llm", "complete")
        assert args["provider_id"] == "p1" and args["model"] == "m9"
        assert args["tools"] == [{"name": "t", "description": "d",
                                  "schema": {"type": "object"}}]

    async def test_reply_text_only(self) -> None:
        llm = ServiceLLM(_call_with_provider({
            "text": "好的。", "tool_calls": [],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }, []))
        reply = await llm.complete(MSGS)
        assert reply.final is True and reply.text == "好的。"


class TestDegraded:
    async def test_no_provider_readable_reply(self) -> None:
        async def call(domain: str, name: str, args: dict) -> list:
            return []  # 无任何已配置提供商

        llm = ServiceLLM(call)
        reply = await llm.complete(MSGS)
        assert reply.final is True
        assert "LLM" in (reply.text or "")

    async def test_provider_error_degrades_to_text(self) -> None:
        async def call(domain: str, name: str, args: dict) -> dict:
            if name == "list_providers":
                return [{"id": "p1", "enabled": True, "has_api_key": True,
                         "default_model": "m9"}]
            raise ServiceError("llm", ErrorSuffix.UNAVAILABLE, "连接超时")

        llm = ServiceLLM(call)
        reply = await llm.complete(MSGS)
        assert reply.final is True
        assert "LLM 调用失败" in (reply.text or "")  # 失败可读,不打断 agent 循环
