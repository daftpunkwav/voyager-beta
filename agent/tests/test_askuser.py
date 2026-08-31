"""询问用户测试(§9.15):问题事件、答案回投、超时兜底、对话闭环。"""

import asyncio

from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, DomainEvent
from platform_eventbus import EventBus, EventLog

from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.main import build_agent
from agent.tools.ask_user import AGENT_ASK, AskUser, Question


async def test_question_event_and_answer(tmp_path) -> None:
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    asker = AskUser(bus)
    q = Question(prompt="选哪个?", kind="choice", options=("A", "B"))
    task = asyncio.create_task(asker.ask(q))
    events: list = []
    for _ in range(50):  # publish 经 to_thread 落库,轮询避免固定短 sleep 竞态
        events = log.read_after(types=[AGENT_ASK])
        if events:
            break
        await asyncio.sleep(0.01)
    assert asker.pending_count == 1
    assert len(events) == 1
    payload = events[0][1].payload
    assert payload["prompt"] == "选哪个?" and payload["options"] == ["A", "B"]
    assert asker.answer(payload["question_id"], "B") is True
    assert await task == "B"
    assert asker.pending_count == 0


async def test_timeout_returns_none(tmp_path) -> None:
    asker = AskUser(None)  # 无总线也应工作(发不出事件,仅等待)
    result = await asker.ask(Question(prompt="在吗?", timeout_s=0.02))
    assert result is None


async def test_answer_unknown_id_misses(tmp_path) -> None:
    asker = AskUser(None)
    assert asker.answer("ghost", 1) is False


class TestChatLoopClosedLoop:
    async def test_askuser_via_chat_then_answer_continues(self, tmp_path) -> None:
        """对话闭环:chat 实例调 ask_user → 前端同路径 answer_question 回投 → agent 继续。

        FakeLLM 脚本:第 1 轮发 choice 提问工具调用;用户作答后第 2 轮给最终回复。
        """
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall(
                    "t1", "ask_user",
                    {"prompt": "选哪个方案?", "kind": "choice", "options": ["A", "B"]},
                ),)),
                LLMReply(text="已按你的选择继续。"),
            ]
        )
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
        run_task = asyncio.create_task(app.master.handle_user_message("帮我选方案"))
        payload = None
        for _ in range(200):  # 等 agent.ask 事件落库(publish 经 to_thread)
            events = app.log.read_after(types=[AGENT_ASK])
            if events:
                payload = events[0][1].payload
                break
            await asyncio.sleep(0.01)
        assert payload is not None, "agent.ask 未发布"
        assert payload["kind"] == "choice" and payload["options"] == ["A", "B"]

        # 与前端 AskDialog 同一条回投路径(agent.answer_question 能力)
        out = await execute(
            app.registry, "answer_question", ActorContext(actor=LOCAL_USER),
            {"question_id": payload["question_id"], "value": "B"},
        )
        assert out["matched"] is True

        await asyncio.wait_for(run_task, timeout=5)  # 入口即返回(回合后台化,phase-15)
        from agent.tests.test_master import _settle

        await _settle(app)  # 等后台回合消化答案并产出最终回复
        replies = [
            e.payload["content"]
            for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
        ]
        assert "已按你的选择继续。" in replies  # agent 在作答后继续并回复
        app.memory.close()
