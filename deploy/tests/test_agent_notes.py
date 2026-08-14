"""agent 写笔记集成:FakeLLM 脚本调 notes__create_note → 落库 + note.created 事件。"""

import time

from fastapi.testclient import TestClient
from platform_contracts import DomainEvent

from agent.llm import FakeLLM, LLMReply, ToolCall
from deploy.backend import build


class TestAgentWritesNotes:
    def test_create_note_via_bridge(self, tmp_path) -> None:
        """对话驱动 agent 调领域能力建笔记:事件 + 摘要列表 + LLM 收到产物 id。"""
        script = [
            LLMReply(tool_calls=(ToolCall(
                id="c1", name="notes__create_note",
                arguments={"title": "ReAct 要点", "content": "感知-行动循环。",
                           "tags": ["方法论"]},
            ),)),
            LLMReply(text="已记录成笔记。"),
        ]
        llm = FakeLLM(script)
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        backend = app.state.backend
        with TestClient(app) as client:
            client.post("/api/chat/messages", json={"content": "把 ReAct 要点记成笔记"})

            # note.created 事件(agent 落库的可靠信号)
            deadline = time.time() + 8
            created = []
            while time.time() < deadline:
                created = [e for _, e in backend.log.read_after(types=["note.created"])]
                if created:
                    break
                time.sleep(0.05)
            assert created, "note.created 未发布"
            note_id = created[-1].payload["note_id"]
            assert created[-1].payload["title"] == "ReAct 要点"

            # 摘要列表可见(用户侧笔记页数据源;摘要无 content 是契约)
            out = client.post("/api/notes/capabilities/list_notes", json={}).json()["result"]
            mine = next(s for s in out if s["id"] == note_id)
            assert mine["title"] == "ReAct 要点"
            assert mine["tags"] == ["方法论"]
            assert "content" not in mine

            # agent 收尾回复且工具结果里带产物 id(供对话中引导用户查看)
            replies = [e for _, e in backend.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
                       if e.payload.get("content") == "已记录成笔记。"]
            assert replies
            tool_result_messages = llm.calls[1]["messages"]
            assert any(note_id in str(m.get("content", "")) for m in tool_result_messages)
