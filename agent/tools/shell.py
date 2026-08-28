"""命令执行工具(经 policy,L2 默认确认;§9.9 shell 维)。

L2 确认是主闸门;此处在执行前再硬拦一眼破坏性命令——即使确认通道
被绕过(无 confirm 的子任务/未来重构),也不放行整机级不可逆操作。

执行走 create_subprocess_exec(argv),不经 shell 解释管道/重定向/通配。
Windows 内建命令(dir/echo)会 FileNotFoundError,不回退 shell=True。
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex

from agent.tools.base import AgentTool

_MAX_OUTPUT = 10_000

# 明确的整机破坏命令(黑名单是最后防线,不做通用解析;正常开发命令不会命中)
_DESTRUCTIVE_RE = re.compile(
    r"\bmkfs(\.\w+)?\b"                      # 格式化文件系统
    r"|\bdd\b[^|;&]*of=/dev/(sd|nvme|vd)"     # dd 直写磁盘设备
    r"|\b(shutdown|halt|reboot|poweroff)\b"   # 关机/重启
    r"|\brm\b[^|;&]*\s-{1,2}[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(/{0,1})(\s|$)"  # rm -rf /
    r"|\brm\b[^|;&]*\s-{1,2}[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(~|\$HOME|%USERPROFILE%)"
    r"|\bformat\s+[a-z]:"                     # Windows 格式化盘符
    r"|\bdiskpart\b"
    r"|\b(curl|wget)\b[^|;\n]*\|\s*(sh|bash|zsh|cmd)"
    r"|\bInvoke-Expression\b"
    r"|\bdel\s+/[sS]\s+/[qQ]\s+[cC]:\\",
    re.IGNORECASE,
)


def shell_tools() -> dict[str, AgentTool]:
    async def run_shell(command: str, timeout: float = 30.0) -> str:
        if _DESTRUCTIVE_RE.search(command):
            return ("[已拒绝] 命令含整机级破坏操作(格式化/关机/根递归删除),"
                    "已被策略硬拦截;如确需执行请在系统终端手动操作")
        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
        except ValueError as exc:
            return f"[已拒绝] 命令无法解析: {exc}"
        if not argv:
            return "[已拒绝] 空命令"
        try:
            proc = await asyncio.create_subprocess_exec(
                argv[0],
                *argv[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            return (
                f"[失败] 找不到可执行文件 {argv[0]!r}。"
                "本工具不经 shell 解释,Windows 内建命令(dir/echo)请改用 "
                "解释器 -c 或给出可执行文件的完整路径。"
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
            description="在本机执行命令(不经 shell;默认需用户确认;输出截断 1 万字)",
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
