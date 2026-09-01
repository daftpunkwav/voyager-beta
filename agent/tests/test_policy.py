"""policy 四维权限测试(§9.9)。"""

from agent.policy import (
    Action,
    AppPolicy,
    FsPolicy,
    Level,
    NetworkPolicy,
    PolicyEngine,
    narrow_network,
)


class TestNetwork:
    def test_off_denies_all(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="off"))
        d = engine.decide(Action(dimension="network", target="https://github.com/x"))
        assert not d.allow
        assert "关闭" in d.reason

    def test_whitelist_suffix_match(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
        assert engine.decide(Action(dimension="network", target="https://api.github.com/x")).allow
        d = engine.decide(Action(dimension="network", target="https://evil.com/x"))
        assert not d.allow
        assert "白名单" in d.reason

    def test_all_allows_with_notify(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="all"))
        d = engine.decide(Action(dimension="network", target="https://example.com"))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_all_rejects_nonglobal_literals(self) -> None:
        """phase-33:ALL 档也不放行环回/链路本地/私网字面量(SSRF);reason 说明缘由。"""
        engine = PolicyEngine(network=NetworkPolicy(mode="all"))
        for target in (
            "http://127.0.0.1/",  # 环回
            "http://localhost:8080/",  # 本机名
            "http://169.254.169.254/",  # 链路本地 / 云元数据
            "http://10.0.0.1/",  # 私网
        ):
            d = engine.decide(Action(dimension="network", target=target))
            assert not d.allow, target
            assert "环回" in d.reason or "内网" in d.reason, target

    def test_nonglobal_beats_whitelist(self) -> None:
        """非全局先于白名单:白名单里写了环回 IP 也不放行。"""
        engine = PolicyEngine(
            network=NetworkPolicy(mode="whitelist", domains=("127.0.0.1",))
        )
        d = engine.decide(Action(dimension="network", target="http://127.0.0.1/"))
        assert not d.allow
        assert "环回" in d.reason or "内网" in d.reason

    def test_userinfo_url_judged_by_real_host(self) -> None:
        """userinfo 形如 https://github.com@evil.com/ 的 URL 实连 evil.com,必须拒绝;
        反向 https://evil.com@github.com/ 实连 github.com(host 解析只看 @ 之后)。"""
        engine = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
        d = engine.decide(Action(dimension="network", target="https://github.com@evil.com/x"))
        assert not d.allow and "evil.com" in d.reason
        assert engine.decide(Action(dimension="network", target="https://evil.com@github.com/x")).allow

    def test_port_does_not_break_match(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
        assert engine.decide(Action(dimension="network", target="https://github.com:8443/x")).allow


class TestFs:
    def test_inside_jail(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        inside = tmp_path / "a.txt"
        inside.touch()
        d = engine.decide(Action(dimension="fs", target=str(inside), write=True))
        assert d.allow and d.level == Level.L1_NOTIFY  # 写 → 提示

    def test_outside_jail_denied(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "evil.txt")))
        assert not d.allow
        assert "工作目录之外" in d.reason

    def test_delete_needs_confirm(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        target = tmp_path / "a.txt"
        d = engine.decide(Action(dimension="fs", target=str(target), irreversible=True))
        assert d.allow and d.level == Level.L2_CONFIRM


class TestFsSkillsGuard:
    """jail 内 skills/ 子树对写删类 fs Action 只读(phase-32):拒绝在 L2 之前。"""

    def test_write_into_skills_denied(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(
            Action(dimension="fs", target=str(tmp_path / "skills" / "pwn" / "SKILL.md"), write=True)
        )
        assert not d.allow
        assert "skill 目录" in d.reason

    def test_read_skills_still_allowed(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "skills" / "pwn" / "SKILL.md")))
        assert d.allow and d.level == Level.L0_SILENT

    def test_write_repo_still_allowed(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "repo" / "a.md"), write=True))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_delete_skills_denied_before_confirm(self, tmp_path) -> None:
        """irreversible 打 skills 直接拒绝,不再进入 L2 确认。"""
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(
            Action(dimension="fs", target=str(tmp_path / "skills" / "keep" / "SKILL.md"), irreversible=True)
        )
        assert not d.allow


class TestFsReadRoots:
    """附加只读根(phase-53,§9.9 文件维):读放行 L0,写/删一律拒绝。"""

    def test_read_inside_read_root_allowed(self, tmp_path) -> None:
        read_root = tmp_path / "docs"
        (read_root / "sub").mkdir(parents=True)
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),)))
        d = engine.decide(Action(dimension="fs", target=str(read_root / "sub" / "a.txt")))
        assert d.allow and d.level == Level.L0_SILENT

    def test_read_root_itself_readable(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(tmp_path / "docs"),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "docs")))
        assert d.allow and d.level == Level.L0_SILENT

    def test_write_in_read_root_denied(self, tmp_path) -> None:
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),)))
        d = engine.decide(Action(dimension="fs", target=str(read_root / "a.txt"), write=True))
        assert not d.allow
        assert "只读" in d.reason

    def test_delete_in_read_root_denied_before_confirm(self, tmp_path) -> None:
        """附加根上的删除不做 L2 确认——确认了也没有写权限,直接拒。"""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),)))
        d = engine.decide(Action(dimension="fs", target=str(read_root / "a.txt"), irreversible=True))
        assert not d.allow
        assert "只读" in d.reason

    def test_outside_all_roots_still_denied(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(tmp_path / "docs"),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "evil.txt")))
        assert not d.allow
        assert "工作目录之外" in d.reason

    def test_workspace_write_unaffected_by_read_roots(self, tmp_path) -> None:
        """workspace 语义回归:roots 优先,附加根不把工作目录变只读。"""
        ws = tmp_path / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), read_roots=(str(tmp_path),)))
        d = engine.decide(Action(dimension="fs", target=str(ws / "a.txt"), write=True))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_read_root_without_roots_rejected(self, tmp_path) -> None:
        """没配附加根时行为与从前一致:workspace 外一律拒绝。"""
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "docs" / "a.txt")))
        assert not d.allow

    def test_relative_path_resolved_against_workspace_not_read_roots(self, tmp_path) -> None:
        """相对路径只以 jail 根为基准(与 fs 工具一致),不会落到附加根:
        a.txt 若按附加根解析则写被拒,按 workspace 解析则写放行 L1。"""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        ws = tmp_path / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), read_roots=(str(read_root),)))
        d = engine.decide(Action(dimension="fs", target="a.txt", write=True))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_escape_via_dotdot_lands_in_read_root_readonly(self, tmp_path) -> None:
        """`..` 逃逸按 resolve 后落点判定:ws/../docs/x 解析后落附加根 → 只读。"""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),)))
        inside = engine.decide(Action(dimension="fs", target=str(tmp_path / "ws" / ".." / "docs" / "a.txt")))
        assert inside.allow and inside.level == Level.L0_SILENT
        write = engine.decide(
            Action(dimension="fs", target=str(tmp_path / "ws" / ".." / "docs" / "a.txt"), write=True)
        )
        assert not write.allow


class TestHotFsReadRootSettings:
    """附加只读根热读(phase-53):不传 settings 用构造快照,传了现读。"""

    def test_settings_override_construction_snapshot(self, tmp_path) -> None:
        read_root = tmp_path / "docs"
        read_root.mkdir()
        settings = _FakeSettings({"agent.fs.read_roots": [str(read_root)]})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        d = engine.decide(Action(dimension="fs", target=str(read_root / "a.txt")))
        assert d.allow and d.level == Level.L0_SILENT
        assert not engine.decide(
            Action(dimension="fs", target=str(read_root / "a.txt"), write=True)
        ).allow

    def test_invalid_settings_falls_back_to_snapshot(self, tmp_path) -> None:
        """坏值(非字符串列表)整份回落快照,不把坏设置当成全拒打残文件读。"""
        settings = _FakeSettings({"agent.fs.read_roots": "not-a-list"})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        assert not engine.decide(Action(dimension="fs", target=str(tmp_path / "docs" / "a.txt"))).allow

    def test_none_settings_value_keeps_snapshot(self, tmp_path) -> None:
        """settings 缺该键(None)时保持构造快照,与 network 热读同语义。"""
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(tmp_path / "docs"),)),
            settings=_FakeSettings({}),
        )
        assert engine.decide(Action(dimension="fs", target=str(tmp_path / "docs" / "a.txt"))).allow


class TestFsWriteRoots:
    """附加读写根(phase-55,§9.9/§9.10):读 L0,写/删 L2;workspace 优先,
    read_roots 兜底只读——判定顺序 roots → write_roots → read_roots → 拒。"""

    def _engine(self, tmp_path, *, write_roots=(), read_roots=()) -> PolicyEngine:
        return PolicyEngine(
            fs=FsPolicy(
                roots=(str(tmp_path / "ws"),),
                read_roots=tuple(read_roots),
                write_roots=tuple(write_roots),
            )
        )

    def test_read_inside_write_root_l0(self, tmp_path) -> None:
        write_root = tmp_path / "proj"
        (write_root / "sub").mkdir(parents=True)
        engine = self._engine(tmp_path, write_roots=(str(write_root),))
        d = engine.decide(Action(dimension="fs", target=str(write_root / "sub" / "a.txt")))
        assert d.allow and d.level == Level.L0_SILENT

    def test_write_inside_write_root_l2_not_l1(self, tmp_path) -> None:
        """用户目录写入不是 workspace 的 L1 提示,须 L2 确认(§9.10)。"""
        write_root = tmp_path / "proj"
        write_root.mkdir()
        engine = self._engine(tmp_path, write_roots=(str(write_root),))
        d = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt"), write=True))
        assert d.allow and d.level == Level.L2_CONFIRM
        assert "确认" in d.reason

    def test_delete_inside_write_root_l2(self, tmp_path) -> None:
        write_root = tmp_path / "proj"
        write_root.mkdir()
        engine = self._engine(tmp_path, write_roots=(str(write_root),))
        d = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt"), irreversible=True))
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_write_in_read_root_only_still_denied(self, tmp_path) -> None:
        """在 read_root 但不在 write_root → 仍拒写(读写根不放宽只读根)。"""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = self._engine(tmp_path, read_roots=(str(read_root),), write_roots=(str(tmp_path / "proj"),))
        d = engine.decide(Action(dimension="fs", target=str(read_root / "a.txt"), write=True))
        assert not d.allow
        assert "只读" in d.reason

    def test_workspace_precedence_over_write_roots(self, tmp_path) -> None:
        """workspace 优先:嵌套在 write_root 下的 workspace 内路径仍走 workspace 规则(写 L1)。"""
        write_root = tmp_path / "proj"
        ws = write_root / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), write_roots=(str(write_root),)))
        d = engine.decide(Action(dimension="fs", target=str(ws / "a.txt"), write=True))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_workspace_skills_guard_not_relaxed_by_write_roots(self, tmp_path) -> None:
        """把 write_root 配到 workspace/skills 上也旁路不了禁写:roots 循环先命中并拒绝。"""
        ws = tmp_path / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), write_roots=(str(ws / "skills"),)))
        d = engine.decide(Action(dimension="fs", target=str(ws / "skills" / "pwn" / "SKILL.md"), write=True))
        assert not d.allow
        assert "skill 目录" in d.reason

    def test_outside_all_roots_still_denied(self, tmp_path) -> None:
        engine = self._engine(tmp_path, write_roots=(str(tmp_path / "proj"),))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "evil.txt")))
        assert not d.allow
        assert "工作目录之外" in d.reason


class TestHotFsWriteRootSettings:
    """附加读写根热读(phase-55):与 read_roots 热读同范式——传 settings 现读,
    缺键/坏值回落构造快照。"""

    def test_settings_override_construction_snapshot(self, tmp_path) -> None:
        write_root = tmp_path / "proj"
        write_root.mkdir()
        settings = _FakeSettings({"agent.fs.write_roots": [str(write_root)]})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        d = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt"), write=True))
        assert d.allow and d.level == Level.L2_CONFIRM
        r = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt")))
        assert r.allow and r.level == Level.L0_SILENT

    def test_invalid_settings_falls_back_to_snapshot(self, tmp_path) -> None:
        """坏值(非字符串列表)整份回落快照,不把坏设置当成全拒打残文件工具。"""
        settings = _FakeSettings({"agent.fs.write_roots": "not-a-list"})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        assert not engine.decide(
            Action(dimension="fs", target=str(tmp_path / "proj" / "a.txt"))
        ).allow

    def test_none_settings_value_keeps_snapshot(self, tmp_path) -> None:
        """settings 缺该键(None)时保持构造快照,与 read_roots 热读同语义。"""
        write_root = tmp_path / "proj"
        write_root.mkdir()
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), write_roots=(str(write_root),)),
            settings=_FakeSettings({}),
        )
        d = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt"), write=True))
        assert d.allow and d.level == Level.L2_CONFIRM


class TestApp:
    def test_whitelist_and_denied(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"set_theme"}), denied=frozenset()))
        assert engine.decide(Action(dimension="app", target="set_theme")).allow
        assert not engine.decide(Action(dimension="app", target="delete_note")).allow

    def test_denied_beats_wildcard(self) -> None:
        engine = PolicyEngine(
            app=AppPolicy(allowed=frozenset({"*"}), denied=frozenset({"danger_op"}))
        )
        assert not engine.decide(Action(dimension="app", target="danger_op")).allow

    def test_prefix_denied(self) -> None:
        engine = PolicyEngine(
            app=AppPolicy(allowed=frozenset({"*"}), denied=frozenset({"notes__*"}))
        )
        assert not engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_prefix_allowed(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"notes__*"})))
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert not engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_irreversible_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="app", target="delete_note", irreversible=True))
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_empty_allowed_denies_all(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset()))
        assert not engine.decide(Action(dimension="app", target="notes__create_note")).allow


class TestShell:
    def test_shell_default_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="rm -rf x"))
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_none_dimension_passthrough(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="none"))
        assert d.allow and d.level == Level.L0_SILENT


class TestShellSkillsGuard:
    """run_shell 命令明显写/删 skills 子树时直接拒绝(phase-41),先于 L2。"""

    def test_redirect_into_skills_denied(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="echo x > skills/pwn.txt", write=True))
        assert not d.allow
        assert "skill 目录" in d.reason

    def test_append_windows_sep_denied(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="echo x >> skills\\pwn.txt", write=True))
        assert not d.allow

    def test_copy_move_delete_skills_denied(self) -> None:
        engine = PolicyEngine()
        for cmd in (
            "rm -rf skills/keep",
            r"del /q skills\keep\SKILL.md",
            "cp a.txt skills/pwn.txt",
            r"move x skills\pwn.txt",
        ):
            d = engine.decide(Action(dimension="shell", target=cmd, write=True))
            assert not d.allow, cmd

    def test_readonly_skills_still_confirm(self) -> None:
        """只读类 skills 命令不拦,维持原 L2 档位。"""
        engine = PolicyEngine()
        for cmd in ("dir skills", r"type skills\keep\SKILL.md", "grep x skills/README.md"):
            d = engine.decide(Action(dimension="shell", target=cmd, write=True))
            assert d.allow and d.level == Level.L2_CONFIRM, cmd

    def test_write_outside_skills_still_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="echo ok > repo/a.txt", write=True))
        assert d.allow and d.level == Level.L2_CONFIRM


class _FakeSettings:
    """最小设置句柄(有 get 即可);value 是 mock 的 settings 库。"""

    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)


class TestHotNetworkSettings:
    """网络判定热读设置(phase-10):不传 settings 仍用构造快照,传了则每次现读。"""

    def test_settings_override_construction_snapshot(self) -> None:
        settings = _FakeSettings({"agent.network.mode": "all",
                                  "agent.network.domains": ["github.com"]})
        engine = PolicyEngine(network=NetworkPolicy(mode="off"), settings=settings)
        d = engine.decide(Action(dimension="network", target="https://example.com"))
        assert d.allow and d.level == Level.L1_NOTIFY  # 构造时 off,判定跟 settings 走

    def test_whitelist_domains_read_from_settings(self) -> None:
        settings = _FakeSettings({"agent.network.mode": "whitelist",
                                  "agent.network.domains": ["pypi.org"]})
        engine = PolicyEngine(network=NetworkPolicy(mode="all"), settings=settings)
        assert engine.decide(Action(dimension="network", target="https://pypi.org/x")).allow
        assert not engine.decide(Action(dimension="network", target="https://github.com/x")).allow

    def test_no_settings_keeps_construction_snapshot(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="off"))
        assert not engine.decide(Action(dimension="network", target="https://github.com/x")).allow

    def test_narrow_network_takes_stricter(self) -> None:
        assert narrow_network("whitelist", "all") == "whitelist"  # 自建全开被夹回全局
        assert narrow_network("whitelist", "off") == "off"  # 自建更严则生效
        assert narrow_network("off", "all") == "off"
        assert narrow_network("all", "all") == "all"
        assert narrow_network("whitelist", "whitelist") == "whitelist"


class TestHotAppSettings:
    """应用内能力白名单热读(phase-19):不传 settings 用构造快照,传了现读。"""

    def test_settings_override_allowed(self) -> None:
        settings = _FakeSettings({"agent.app.allowed": ["notes__create_note"],
                                  "agent.app.denied": []})
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})), settings=settings)
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert not engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_settings_denied_beats_wildcard(self) -> None:
        settings = _FakeSettings({"agent.app.allowed": ["*"],
                                  "agent.app.denied": ["notes__delete_note"]})
        engine = PolicyEngine(app=AppPolicy(), settings=settings)
        assert not engine.decide(Action(dimension="app", target="notes__delete_note")).allow
        assert engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_settings_prefix_denied(self) -> None:
        settings = _FakeSettings({"agent.app.allowed": ["*"],
                                  "agent.app.denied": ["notes__*"]})
        engine = PolicyEngine(app=AppPolicy(), settings=settings)
        assert not engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_invalid_settings_falls_back_to_snapshot(self) -> None:
        settings = _FakeSettings({"agent.app.allowed": "not-a-list",
                                  "agent.app.denied": ["notes__delete_note"]})
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})), settings=settings)
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow

    def test_no_settings_keeps_construction_snapshot(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})))
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow
