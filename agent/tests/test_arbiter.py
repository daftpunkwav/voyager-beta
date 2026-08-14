"""消息仲裁测试(§9.7):排队默认;auto 判官并入;guide 排队并提示。"""

from agent.llm import FakeLLM, LLMReply
from agent.master.arbiter import Arbiter, ArbiterMode


class TestArbiter:
    async def test_queue_default_no_llm_call(self) -> None:
        llm = FakeLLM()
        arbiter = Arbiter(llm)
        d = await arbiter.decide("新消息", "当前任务", mode=ArbiterMode.QUEUE)
        assert d.action == "enqueue"
        assert llm.calls == []  # 排队模式不消耗判官 token

    async def test_auto_merge_when_related(self) -> None:
        arbiter = Arbiter(FakeLLM([LLMReply(text="merge")]))
        d = await arbiter.decide("补充:用 Python 3.12", "分析项目", mode=ArbiterMode.AUTO)
        assert d.action == "merge"

    async def test_auto_enqueue_when_new_intent(self) -> None:
        arbiter = Arbiter(FakeLLM([LLMReply(text="enqueue")]))
        d = await arbiter.decide("帮我做 PPT", "分析项目", mode=ArbiterMode.AUTO)
        assert d.action == "enqueue"

    async def test_guide_notifies_on_new_intent(self) -> None:
        arbiter = Arbiter(FakeLLM([LLMReply(text="enqueue")]))
        d = await arbiter.decide("帮我做 PPT", "分析项目", mode=ArbiterMode.GUIDE)
        assert d.action == "enqueue_notify"
        assert "先做这个" in d.reason
