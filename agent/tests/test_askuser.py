"""询问用户测试(§9.15):问题事件、答案回投、超时兜底。"""

import asyncio

from platform_eventbus import EventBus, EventLog

from agent.tools.ask_user import AGENT_ASK, AskUser, Question


async def test_question_event_and_answer(tmp_path) -> None:
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    asker = AskUser(bus)
    q = Question(prompt="选哪个?", kind="choice", options=("A", "B"))
    task = asyncio.create_task(asker.ask(q))
    await asyncio.sleep(0.01)  # 等事件落库
    assert asker.pending_count == 1
    events = log.read_after(types=[AGENT_ASK])
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
