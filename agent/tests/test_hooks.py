"""hook 真触发测试(phase-11,§9.13):pre_tool 拦截、post_tool 成败都发、
声明式 hook 的 on 两种含义、build_agent 挂载用户 hooks 目录与事件转发。"""

import json
import logging
from types import SimpleNamespace

from agent.hooks import HOOK_POINTS, HookLoader, HookRegistry
from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent
from agent.policy import PolicyEngine
from agent.tools import AgentTool, Toolbelt


def _belt(hooks: HookRegistry | None) -> Toolbelt:
    def echo(text: str = "") -> str:
        return f"echo:{text}"

    def boom() -> str:
        raise ValueError("炸了")

    return Toolbelt(
        {
            "echo": AgentTool(name="echo", description="回声", handler=echo),
            "boom": AgentTool(name="boom", description="必炸", handler=boom),
        },
        PolicyEngine(),
        hooks=hooks,
    )


class TestToolLifecycleHooks:
    async def test_pre_tool_false_intercepts(self) -> None:
        """pre_tool 任一返回 False:handler 不执行,其余 pre hook 仍被触发。"""
        calls: list[str] = []

        async def block(**kwargs) -> bool:
            return False

        async def watch(**kwargs) -> None:
            calls.append("watch")

        hooks = HookRegistry()
        hooks.register("pre_tool", block, source="t")
        hooks.register("pre_tool", watch, source="t")
        out = await _belt(hooks).call(ToolCall("1", "echo", {"text": "hi"}))
        assert out.startswith("[已拦截]")
        assert calls == ["watch"]

    async def test_pre_tool_pass_through(self) -> None:
        async def allow(**kwargs) -> None:
            return None

        hooks = HookRegistry()
        hooks.register("pre_tool", allow, source="t")
        out = await _belt(hooks).call(ToolCall("1", "echo", {"text": "hi"}))
        assert out == "echo:hi"

    async def test_post_tool_success_and_failure(self) -> None:
        """成功与失败都要 post,让 hook 看见调用结果。"""
        seen: list[dict] = []

        async def post(**kwargs) -> None:
            seen.append(kwargs)

        hooks = HookRegistry()
        hooks.register("post_tool", post, source="t")
        belt = _belt(hooks)
        await belt.call(ToolCall("1", "echo", {"text": "a"}))
        await belt.call(ToolCall("2", "boom", {}))
        assert [s["ok"] for s in seen] == [True, False]
        assert seen[0]["name"] == "echo" and seen[0]["result"] == "echo:a"
        assert seen[1]["name"] == "boom"

    def test_views_copy_hooks(self) -> None:
        """trimmed / with_policy / with_active 派生视图不丢 hook 注册表。"""
        hooks = HookRegistry()
        belt = _belt(hooks)
        assert belt.trimmed(["echo"])._hooks is hooks
        assert belt.with_policy(PolicyEngine())._hooks is hooks
        assert belt.with_active(set())._hooks is hooks


class TestDeclarativeHooks:
    def _load(self, tmp_path, data: dict) -> HookRegistry:
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir(exist_ok=True)
        (d / "h.json").write_text(json.dumps(data), encoding="utf-8")
        HookLoader(hooks).load_dir(d, source="user", approved=True)
        return hooks

    def test_hook_point_registers_directly(self, tmp_path) -> None:
        hooks = self._load(tmp_path, {"on": "on_user_message", "enabled": True})
        assert hooks.registered() == {"on_user_message": 1}

    async def test_event_name_wraps_on_event(self, tmp_path, caplog) -> None:
        """note.created 不必进 HOOK_POINTS:包装成 on_event 过滤器按事件类型命中。"""
        assert "note.created" not in HOOK_POINTS  # 事件名与生命周期点不混名(契约前提)
        hooks = self._load(
            tmp_path, {"on": "note.created", "description": "笔记新建", "enabled": True}
        )
        assert hooks.registered() == {"on_event": 1}
        with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
            await hooks.fire("on_event", event=SimpleNamespace(type="note.created"))
            await hooks.fire("on_event", event=SimpleNamespace(type="note.deleted"))
        assert sum("笔记新建" in r.message for r in caplog.records) == 1

    def test_disabled_or_unapproved_skipped(self, tmp_path) -> None:
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "a.json").write_text(
            json.dumps({"on": "note.created", "enabled": False}), encoding="utf-8"
        )
        assert HookLoader(hooks).load_dir(d, source="user", approved=False) == 0
        assert HookLoader(hooks).load_dir(d, source="user", approved=True) == 0
        assert hooks.registered() == {}


class TestBuildAgentWiring:
    def _build(self, tmp_path):
        return build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )

    def test_default_no_hooks_loaded(self, tmp_path) -> None:
        """默认装配:用户 hooks 目录为空,plugins/_example 不加载;
        订阅恰好四条领域类型,无 "*"(phase-28 精确订阅)。"""
        app = self._build(tmp_path)
        try:
            assert app.hooks.registered() == {}
            assert app.loop.patterns == (
                "user.message",
                "user.online",
                "source.ready",
                "user.activity",
            )
        finally:
            app.memory.close()

    def test_user_hooks_dir_loaded(self, tmp_path) -> None:
        hooks_dir = tmp_path / "ws" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "note-watch.json").write_text(
            json.dumps({"on": "note.created", "description": "用户 hook", "enabled": True}),
            encoding="utf-8",
        )
        app = self._build(tmp_path)
        try:
            assert app.hooks.registered() == {"on_event": 1}
            # 声明式 hook 的事件 pattern 进订阅;"*" 仍不出现(phase-28)
            assert "note.created" in app.loop.patterns
            assert "*" not in app.loop.patterns
        finally:
            app.memory.close()

    async def test_loop_forwards_events_to_on_event(self, tmp_path) -> None:
        """进入 loop 的事件经 relay 交给 on_event(phase-28 起无 "*" handler)。

        这里直接调 _dispatch,只锁 relay 转发本身;live 总线上任意事件
        不再进 agent——订阅由 patterns 精确决定(见 test_user_hooks_dir_loaded)。
        """
        app = self._build(tmp_path)
        try:
            assert "*" not in app.loop._handlers  # "*" 已被禁止,relay 取代
            seen: list[str] = []

            async def spy(event) -> None:
                seen.append(event.type)

            app.hooks.register("on_event", spy, source="test")
            await app.loop._dispatch(
                SimpleNamespace(type="note.created", trace_id=None, payload={})
            )
            assert seen == ["note.created"]
        finally:
            app.memory.close()
