"""policy 四维权限测试(§9.9)。"""

from agent.policy import (
    Action,
    AppPolicy,
    FsPolicy,
    Level,
    NetworkPolicy,
    PolicyEngine,
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

    def test_irreversible_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="app", target="delete_note", irreversible=True))
        assert d.allow and d.level == Level.L2_CONFIRM


class TestShell:
    def test_shell_default_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="rm -rf x"))
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_none_dimension_passthrough(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="none"))
        assert d.allow and d.level == Level.L0_SILENT
