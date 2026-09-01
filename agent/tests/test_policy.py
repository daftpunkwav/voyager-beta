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
