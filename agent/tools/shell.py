"""命令执行工具(经 policy,L2 默认确认;§9.9 shell 维)。"""

from __future__ import annotations

import asyncio

from agent.tools.base import AgentTool

_MAX_OUTPUT = 10_000


def shell_tools() -> dict[str, AgentTool]:
    async def run_shell(command: str, timeout: float = 30.0) -> str:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            return f"[超时] {timeout}s 未结束,已终止"
        text = out.decode("utf-8", errors="replace")
        if len(text) > _MAX_OUTPUT:
            text = text[:_MAX_OUTPUT] + "\n…[截断]"
        return f"exit={proc.returncode}\n{text}"

    return {
        "run_shell": AgentTool(
            name="run_shell",
            description="在本机执行 shell 命令(默认需用户确认;输出截断 1 万字)",
            handler=run_shell,
            dimension="shell",
            write=True,
            schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "number"},
                },
                "required": ["command"],
            },
        )
    }
