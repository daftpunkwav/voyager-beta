"""L1 权限提示事件接线(phase-40,§9.9):生产 Toolbelt 带 notify,调用后发 agent.policy.notify。"""

import asyncio

from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent


class TestPolicyNotify:
    async def test_l1_tool_call_emits_notify_event(self, tmp_path) -> None:
        """jail 内 write_file 是 L1_NOTIFY:invoke 发 notify 后工具照常执行,
        事件 log 里应有一条 agent.policy.notify(文案含工具名与 target)。"""
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )
        try:
            (tmp_path / "ws" / "f.txt").write_text("x", encoding="utf-8")
            out = await app.spawner._toolbelt.call(
                ToolCall("1", "write_file", {"path": "g.txt", "content": "y"})
            )
            assert "written" in out  # L1 只提示不拦截,工具照常执行
            rows: list = []
            for _ in range(20):  # publish 经 to_thread 落库,轮询等落库(phase-40)
                rows = app.log.read_after(after_seq=0, types=("agent.policy.notify",))
                if rows:
                    break
                await asyncio.sleep(0.05)
            assert rows, "L1 调用后应至少有一条 agent.policy.notify"
            _seq, ev = rows[0]
            assert "write_file" in ev.payload["message"]
            assert "g.txt" in ev.payload["message"]
        finally:
            app.close()
