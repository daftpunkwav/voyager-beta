"""工具带与工作目录测试:fs jail、能力面裁剪、L1/L2 确认通道(§9.4/§9.9/§9.10)。"""

import sys
from pathlib import Path

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

    async def test_skills_write_denied(self, workdir) -> None:
        """skills/ 禁写(phase-32):policy 层拒绝,文件不落盘。"""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": "skills/pwn/SKILL.md", "content": "pwn"})
        )
        assert "[已拒绝]" in out
        assert not (workdir / "skills").exists()  # 连父目录都不许建

    async def test_skills_write_via_dotdot_denied(self, workdir) -> None:
        """repo/../skills 解析后仍在 skills 下,同样拒绝。"""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": "repo/../skills/pwn/SKILL.md", "content": "pwn"})
        )
        assert "[已拒绝]" in out
        assert not (workdir / "skills" / "pwn").exists()

    async def test_skills_delete_denied_without_confirm(self, workdir) -> None:
        """delete 打 skills 直接拒绝,不弹 L2 确认;文件保留。"""
        asked: list[str] = []

        async def spy_confirm(prompt: str) -> bool:
            asked.append(prompt)
            return True

        keep = workdir / "skills" / "keep" / "SKILL.md"
        keep.parent.mkdir(parents=True)
        keep.write_text("# keep\n", encoding="utf-8")
        belt = _belt(workdir, confirm=spy_confirm)
        out = await belt.call(ToolCall("1", "delete_file", {"path": "skills/keep/SKILL.md"}))
        assert "[已拒绝]" in out
        assert keep.exists()
        assert asked == []  # 拒绝发生在确认之前,确认通道根本没被问

    async def test_skills_read_list_still_ok(self, workdir) -> None:
        keep = workdir / "skills" / "keep" / "SKILL.md"
        keep.parent.mkdir(parents=True)
        keep.write_text("# keep\n", encoding="utf-8")
        belt = _belt(workdir)
        text = await belt.call(ToolCall("1", "read_file", {"path": "skills/keep/SKILL.md"}))
        assert "# keep" in text
        listing = await belt.call(ToolCall("2", "list_dir", {"path": "skills"}))
        assert "keep/" in listing

    async def test_repo_write_regression(self, workdir) -> None:
        """非 skills 分类仍可写(回归)。"""
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "write_file", {"path": "repo/a.md", "content": "x"}))
        assert "written" in out


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


class TestAppPolicyTarget:
    async def test_app_dimension_uses_tool_name_not_url(self) -> None:
        """app 维判定用工具名做 target,带 url 参数的桥工具仍按工具名命中(phase-19)。"""
        from agent.llm import ToolCall
        from agent.policy import AppPolicy, PolicyEngine
        from agent.tools import AgentTool, Toolbelt

        async def handler(url: str = "") -> dict:
            return {"ok": True, "url": url}

        tool = AgentTool(
            name="notes__create_note", description="写笔记", handler=handler,
            schema={"url": {"type": "string"}}, dimension="app", write=True,
        )
        allowed = Toolbelt(
            {"notes__create_note": tool},
            PolicyEngine(app=AppPolicy(allowed=frozenset({"notes__create_note"}))),
        )
        out = await allowed.call(ToolCall("1", "notes__create_note", {"url": "https://evil.com"}))
        assert "ok" in out

        denied = Toolbelt(
            {"notes__create_note": tool},
            PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}), denied=frozenset({"notes__create_note"}))),
        )
        out = await denied.call(ToolCall("2", "notes__create_note", {"url": "https://github.com"}))
        assert "[已拒绝]" in out


class TestShellGuard:
    async def test_destructive_commands_blocked(self, tmp_path) -> None:
        """整机级破坏命令在执行前被硬拦截(即使 L2 确认通道缺失)。"""
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        for cmd in ("mkfs.ext4 /dev/sda1", "dd if=a of=/dev/sda",
                    "shutdown now", "rm -rf /", "rm -rf ~", "format C: /q"):
            out = await run_shell(cmd, timeout=2)
            assert "[已拒绝]" in out, cmd

    async def test_normal_command_not_blocked(self, tmp_path) -> None:
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        # 不经 shell:解释器 -c 避免 Windows 内建 echo;无嵌套引号以免 shlex 在 nt 模式拆错
        out = await run_shell(f"{sys.executable} -c print(42)", timeout=5)
        assert "已拒绝" not in out and "42" in out

    async def test_missing_executable_does_not_fall_back_to_shell(self, tmp_path) -> None:
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        # 不用 echo:Unix 上 /bin/echo 真实存在,测不到「不回退 shell」
        out = await run_shell("__no_such_cmd_xyz__", timeout=5)
        assert "[失败]" in out and "找不到可执行文件" in out

    async def test_subprocess_cwd_pinned_to_workspace(self, tmp_path) -> None:
        """子进程 cwd 钉在装配目录(phase-35):相对路径脚本可被找到,
        相对写出的文件落在该目录,不落进程 cwd / 父目录。"""
        work = tmp_path / "ws"
        work.mkdir()
        probe = work / "_cwd_probe.py"
        probe.write_text(
            "from pathlib import Path\n"
            "Path('cwd-probe-phase35.txt').write_text('ok', encoding='utf-8')\n",
            encoding="utf-8",
        )
        run_shell = shell_tools(work)["run_shell"].handler
        stray = Path.cwd() / "cwd-probe-phase35.txt"
        try:
            out = await run_shell(f"{sys.executable} {probe.name}", timeout=5)
            assert "exit=0" in out, out
            assert (work / "cwd-probe-phase35.txt").read_text(encoding="utf-8") == "ok"
            assert not (tmp_path / "cwd-probe-phase35.txt").exists()  # 不落父目录
            # 实现漏传 cwd= 时文件会落到进程 cwd,这条会红
            if Path.cwd().resolve() != work.resolve():
                assert not stray.exists()
        finally:
            # 防实现漏 cwd= 时弄脏仓库根:进程 cwd 残留同名文件则清理
            if stray.exists():
                stray.unlink()

    async def test_shell_skills_write_denied_by_policy(self, workdir) -> None:
        """phase-41:policy 层拒绝经 shell 写 skills,先于 L2;文件不落盘。"""
        belt = Toolbelt(
            {**fs_tools([workdir]), **shell_tools(workdir)},
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "run_shell", {"command": "echo pwn > skills/x.txt"}))
        assert "[已拒绝]" in out
        assert not (workdir / "skills" / "x.txt").exists()

    async def test_shell_readonly_skills_still_needs_confirm(self, workdir) -> None:
        """只读类 skills 命令不被新闸门误杀:无确认通道时仍 [需确认](L2 不变)。"""
        belt = Toolbelt(
            {**fs_tools([workdir]), **shell_tools(workdir)},
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(
            ToolCall("1", "run_shell", {"command": "type skills\\keep\\SKILL.md"})
        )
        assert "[需确认]" in out


class TestFsReadRoots:
    """附加只读根端到端(phase-53,§9.9):policy 与工具层双层同语义——
    读工具放行附加根,写/删双层都拒。"""

    def _belt_with_read_root(self, workdir, docs) -> Toolbelt:
        return Toolbelt(
            fs_tools([workdir], read_roots=[docs]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),), read_roots=(str(docs),))),
        )

    async def test_read_file_in_read_root_allowed(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("附加根内容", encoding="utf-8")
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(ToolCall("1", "read_file", {"path": str(docs / "a.txt")}))
        assert "附加根内容" in out

    async def test_list_dir_in_read_root_allowed(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        (docs / "sub").mkdir(parents=True)
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(ToolCall("1", "list_dir", {"path": str(docs)}))
        assert "sub/" in out

    async def test_write_in_read_root_denied(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": str(docs / "pwn.txt"), "content": "x"})
        )
        assert "[已拒绝]" in out
        assert not (docs / "pwn.txt").exists()

    async def test_delete_in_read_root_denied_without_confirm(self, workdir, tmp_path) -> None:
        """附加根删除直接拒绝,不弹 L2 确认;文件保留。"""
        docs = tmp_path / "docs"
        docs.mkdir()
        target = docs / "keep.txt"
        target.write_text("keep", encoding="utf-8")
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(ToolCall("1", "delete_file", {"path": str(target)}))
        assert "[已拒绝]" in out
        assert target.exists()

    async def test_read_outside_all_roots_still_denied(self, workdir, tmp_path) -> None:
        """未配附加根(或路径在所有根之外)时,读也双层拒绝——旧行为回归。"""
        belt = Toolbelt(
            fs_tools([workdir]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "read_file", {"path": str(tmp_path / "evil.txt")}))
        assert "[已拒绝]" in out

    async def test_hot_read_roots_fn_without_rebuild(self, workdir, tmp_path) -> None:
        """read_roots_fn 热读:改 settings 后 policy 与工具层同步放行,无需重建 Toolbelt。"""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("热读内容", encoding="utf-8")
        values: dict[str, list[str]] = {"agent.fs.read_roots": []}
        settings = _FakeSettings(values)
        belt = Toolbelt(
            fs_tools(
                [workdir],
                read_roots=[],
                read_roots_fn=lambda: list(settings.get("agent.fs.read_roots") or ()),
            ),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),)), settings=settings),
        )
        denied = await belt.call(ToolCall("1", "read_file", {"path": str(docs / "a.txt")}))
        assert "[已拒绝]" in denied
        values["agent.fs.read_roots"] = [str(docs)]
        allowed = await belt.call(ToolCall("2", "read_file", {"path": str(docs / "a.txt")}))
        assert "热读内容" in allowed


class _FakeSettings:
    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)
