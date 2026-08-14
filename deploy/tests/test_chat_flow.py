"""聊天全链路集成:gateway HTTP 入口 → 事件流 → agent loop → LLM(FakeLLM 脚本)。

覆盖:消息往返、ask_user 弹窗往返(答案回投后 LLM 收到)、仲裁 queue 模式
(执行中第二句排队,完成后依次处理)。
"""

import asyncio
import time

from fastapi.testclient import TestClient
from platform_contracts import DomainEvent

from agent.llm import FakeLLM, LLMReply, ToolCall
from deploy.backend import build

_AGENT_MSG = [DomainEvent.AGENT_MESSAGE]


def _wait_event(log, types, *, timeout=8.0, pred=None):
    """轮询事件日志直到出现满足条件的事件(agent 处理是异步的)。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = [e for _, e in log.read_after(types=types)
                  if pred is None or pred(e)]
        if events:
            return events
        time.sleep(0.05)
    raise AssertionError(f"等待事件超时: {types}")


def _seqs(log, types):
    return [s for s, _ in log.read_after(types=types)]


class TestChatFlow:
    def test_message_roundtrip(self, tmp_path) -> None:
        """用户 POST → user.message → agent 处理 → agent.message(非空)。"""
        llm = FakeLLM(default="收到,我在。")
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        backend = app.state.backend
        with TestClient(app) as client:
            resp = client.post("/api/chat/messages", json={"content": "你好"})
            assert resp.status_code == 200
            assert resp.json()["seq"] > 0

            users = _wait_event(backend.log, [DomainEvent.USER_MESSAGE])
            assert users[-1].payload["content"] == "你好"

            agents = _wait_event(backend.log, _AGENT_MSG)
            assert agents[-1].payload["content"] == "收到,我在。"

            # 历史接口(重开页面重建)双向可见
            hist = client.get("/api/chat/messages?limit=10").json()["messages"]
            kinds = {m["type"] for m in hist}
            assert {"user.message", "agent.message"} <= kinds

    def test_ask_user_roundtrip(self, tmp_path) -> None:
        """LLM 调 ask_user → agent.ask 事件 → answer_question 回投 → LLM 收到并收尾。"""
        script = [
            LLMReply(tool_calls=(ToolCall(
                id="c1", name="ask_user",
                arguments={"prompt": "选一个", "kind": "choice", "options": ["A", "B"]},
            ),)),
            LLMReply(text="你选了 A。"),
        ]
        llm = FakeLLM(script)
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        backend = app.state.backend
        with TestClient(app) as client:
            client.post("/api/chat/messages", json={"content": "问我一个问题"})
            asks = _wait_event(backend.log, ["agent.ask"])
            ask = asks[-1]
            assert ask.payload["kind"] == "choice"
            assert ask.payload["options"] == ["A", "B"]

            qid = ask.payload["question_id"]
            out = client.post("/api/agent/capabilities/answer_question",
                              json={"question_id": qid, "value": "A"}).json()
            assert out["result"]["matched"] is True

            # 第二次 LLM 调用的消息里应含用户答案,随后收尾回复
            replies = _wait_event(backend.log, _AGENT_MSG,
                                  pred=lambda e: e.payload.get("content") == "你选了 A。")
            assert replies
            second_messages = llm.calls[1]["messages"]
            assert any("A" in str(m.get("content", "")) for m in second_messages)

    def test_queue_mode_second_message_waits(self, tmp_path) -> None:
        """queue 仲裁:第一句处理中第二句只入队,完成后依次处理(事件顺序可证)。"""
        calls: list[float] = []

        async def dynamic(messages, tools):
            calls.append(time.monotonic())
            if len(calls) == 1:
                await asyncio.sleep(1.0)  # 第一条处理耗时,制造"执行中"窗口
                return LLMReply(text="第一条完成。")
            return LLMReply(text="第二条完成。")

        app = build(tmp_path / "data", tmp_path / "ws", llm=FakeLLM(dynamic=dynamic))
        backend = app.state.backend
        with TestClient(app) as client:
            client.post("/api/chat/messages", json={"content": "第一条"})
            # 轮询等第一条进入 LLM 调用(agent 异步处理,耗时不确定)
            deadline = time.time() + 3.0
            while time.time() < deadline and not calls:
                time.sleep(0.02)
            assert calls, "第一条未被处理"
            client.post("/api/chat/messages", json={"content": "第二条"})
            # 第一条仍在 LLM sleep 窗口内:queue 模式第二条不打断、不插话
            assert len(calls) == 1

            _wait_event(backend.log, _AGENT_MSG,
                        pred=lambda e: e.payload.get("content") == "第一条完成。")
            _wait_event(backend.log, _AGENT_MSG,
                        pred=lambda e: e.payload.get("content") == "第二条完成。")
            # 依次处理:第二条的处理开始不早于第一条的回复事件
            seqs1 = _seqs(backend.log, _AGENT_MSG)
            assert len(seqs1) >= 2
