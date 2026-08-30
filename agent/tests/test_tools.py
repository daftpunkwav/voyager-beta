"""工具带与工作目录测试:fs jail、能力面裁剪、L1/L2 确认通道(§9.4/§9.9/§9.10)。"""

import sys

import pytest

from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, ensure_workdir, fs_tools
from agent.tools.shell import shell_tools


@pytest.fixture()
def workdir(tmp_path):
    root = ensure_workdir(tmp_path / "workspace")
    return root


def _belt(root, *, confirm=None, notify=None) -> Toolbelt:
    return Toolbelt(
        fs_tools([root]), PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        confirm=confirm, notify=notify,
    )


class TestFsJail:
    async def test_write_read_list_delete(self, workdir) -> None:
        belt = _belt(workdir, confirm=lambda _p: _yes())
        assert "repo/" in await belt.call(ToolCall("1", "list_dir", {"path": "."}))
        await belt.call(ToolCall("2", "write_file", {"path": "repo/a.md", "content": "你好"}))
        assert "你好" in await belt.call(ToolCall("3", "read_file", {"path": "repo/a.md"}))
        out = await belt.call(ToolCall("4", "delete_file", {"path": "repo/a.md"}))
        assert "deleted" in out

    async def test_outside_jail_rejected_twice(self, workdir, tmp_path) -> None:
        """内层 jail + 外层 policy 双层防护。"""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": str(tmp_path / "evil.txt"), "content": "x"})
        )
        assert "[已拒绝]" in out
        assert not (tmp_path / "evil.txt").exists()

    def test_ensure_workdir_categories(self, workdir) -> None:
        for cat in ("repo", "books", "news", "exports", "imports", "sandbox"):
            assert (workdir / cat).is_dir()


async def _yes() -> bool:
    return True


class TestTrim:
    def test_trimmed_removes_write(self, workdir) -> None:
        """不给 write 就是真没有(§9.4.1)。"""
        belt = _belt(workdir).trimmed(["read_file"])
        assert belt.names() == ["read_file"]
        assert belt._policy is not None  # 裁剪不丢权限引擎

    async def test_trimmed_call_blocked(self, workdir) -> None:
        belt = _belt(workdir).trimmed(["read_file"])
        out = await belt.call(ToolCall("1", "write_file", {"path": "a", "content": "b"}))
        assert "[未知工具]" in out

    def test_trimmed_prefix_expand_relative_to_belt(self, workdir) -> None:
        """前缀授予(phase-06):相对当前名册展开,白名单外的新前缀名不进来。"""
        belt = _belt(workdir)
        trimmed = belt.trimmed(["read_*", "list_dir"])
        assert set(trimmed.names()) == {"read_file", "list_dir"}
        # 名册里没有 notes__* 域:前缀不凭空造工具
        assert not any(n.startswith("notes__") for n in trimmed.names())

    def test_trimmed_bare_star_is_not_prefix(self, workdir) -> None:
        """裸 `*` 不是合法前缀授予(避免一笔放开全量名册)。"""
        belt = _belt(workdir).trimmed(["*"])
        assert belt.names() == []


class TestConfirmFlow:
    async def test_l2_confirm_approve_and_deny(self, workdir) -> None:
        asked: list[str] = []
        (workdir / "f.txt").touch()

        async def nope(_prompt: str) -> bool:
            asked.append(_prompt)
            return False

        belt = _belt(workdir, confirm=nope)
        out = await belt.call(ToolCall("1", "delete_file", {"path": "f.txt"}))
        assert "[已取消]" in out and asked  # 确认问题确实发出
        assert (workdir / "f.txt").exists()  # 未删除

    async def test_l2_without_channel_skipped(self, workdir) -> None:
        (workdir / "f.txt").touch()
        belt = _belt(workdir)  # 无 confirm 通道
        out = await belt.call(ToolCall("1", "delete_file", {"path": "f.txt"}))
        assert "[需确认]" in out
        assert (workdir / "f.txt").exists()

    async def test_l1_notify_fired(self, workdir) -> None:
        seen: list[str] = []
        (workdir / "f.txt").write_text("x")

        async def notify(msg: str) -> None:
            seen.append(msg)

        belt = _belt(workdir, notify=notify)
        await belt.call(ToolCall("1", "write_file", {"path": "g.txt", "content": "y"}))
        assert seen and "write_file" in seen[0]

    async def test_unknown_tool(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "nope", {}))
        assert "[未知工具]" in out


class TestShellGuard:
    async def test_destructive_commands_blocked(self) -> None:
        """整机级破坏命令在执行前被硬拦截(即使 L2 确认通道缺失)。"""
        run_shell = shell_tools()["run_shell"].handler
        for cmd in ("mkfs.ext4 /dev/sda1", "dd if=a of=/dev/sda",
                    "shutdown now", "rm -rf /", "rm -rf ~", "format C: /q"):
            out = await run_shell(cmd, timeout=2)
            assert "[已拒绝]" in out, cmd

    async def test_normal_command_not_blocked(self) -> None:
        run_shell = shell_tools()["run_shell"].handler
        # 不经 shell:解释器 -c 避免 Windows 内建 echo;无嵌套引号以免 shlex 在 nt 模式拆错
        out = await run_shell(f"{sys.executable} -c print(42)", timeout=5)
        assert "已拒绝" not in out and "42" in out

    async def test_missing_executable_does_not_fall_back_to_shell(self) -> None:
        run_shell = shell_tools()["run_shell"].handler
        # 不用 echo:Unix 上 /bin/echo 真实存在,测不到「不回退 shell」
        out = await run_shell("__voyager_no_such_cmd_xyz__", timeout=5)
        assert "[失败]" in out and "找不到可执行文件" in out
