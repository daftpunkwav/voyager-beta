"""用户 workspace/hooks 热装热卸测试(phase-78,§9.13)。

覆盖:reload 服务(卸旧仅 user: 前缀、重装、选择性撤订阅、坏文件披露)、
能力契约(USER 限定、无路径参数)、与插件/EventLoop 共存(插件订阅不误撤)、
live loop 集成(reload 后同进程 publish 触发;对标 phase-75
TestRunTimeSubscription 的集成风格)。启动装载路径回归由 test_hooks 锁定。
"""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import (
    LOCAL_USER,
    ActorKind,
    ActorRef,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus, EventLog

from agent.hooks import HookLoader, HookRegistry, UserHookReloader
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.runtime import EventLoop

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


def _write_hook(hooks_dir: Path, name: str, data: dict) -> Path:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    path = hooks_dir / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _reloader(
    tmp_path, *, registry: HookRegistry | None = None, plugins=None
) -> tuple[UserHookReloader, Path, HookRegistry]:
    """(reloader, hooks_dir, registry) 三元组;目录钉死 tmp_path/ws/hooks。"""
    reg = registry if registry is not None else HookRegistry()
    hooks_dir = tmp_path / "ws" / "hooks"
    return UserHookReloader(reg, hooks_dir, plugins=plugins), hooks_dir, reg


def _make_plugin(root: Path, name: str = "example", *, enabled: bool = True) -> Path:
    """最小声明式插件:on note.created 的 hook(无 skill/MCP,够判定链用)。"""
    d = root / name
    d.mkdir(parents=True)
    (d / "plugin.json").write_text(
        json.dumps({
            "name": name,
            "version": "0.1.0",
            "description": "测试插件",
            "permissions": {"scopes": [], "network": "off", "fs": "none"},
            "contains": {"skills": [], "hooks": ["hooks/on-note.json"], "mcp": None},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    hook_dir = d / "hooks"
    hook_dir.mkdir()
    (hook_dir / "on-note.json").write_text(
        json.dumps({"on": "note.created", "description": f"{name} hook", "enabled": enabled}),
        encoding="utf-8",
    )
    return d


class TestRegistryOwnership:
    """HookRegistry 的 pattern 归属记录(phase-78 新增辅助)。"""

    def test_record_with_source_tracks_owners(self) -> None:
        hooks = HookRegistry()
        hooks.record_event_pattern("note.created", source="user:a")
        hooks.record_event_pattern("note.created", source="plugin:x:h")
        hooks.record_event_pattern("note.created", source="user:a")  # 重复幂等
        assert hooks.pattern_owner_sources("note.created") == ("plugin:x:h", "user:a")
        assert hooks.pattern_owner_sources("ghost.*") == ()

    def test_forget_clears_owners(self) -> None:
        hooks = HookRegistry()
        hooks.record_event_pattern("note.created", source="user:a")
        hooks.forget_event_pattern("note.created")
        assert hooks.event_patterns == ()
        assert hooks.pattern_owner_sources("note.created") == ()

    def test_remove_source_keeps_owners(self) -> None:
        """remove_source 既有语义不动 owner 记录:撤订阅由调用方显式 forget。"""
        hooks = HookRegistry()
        hooks.record_event_pattern("note.created", source="user:a")
        hooks.register("on_event", lambda **kw: None, source="user:a")
        assert hooks.remove_source("user:") == 1
        assert hooks.pattern_owner_sources("note.created") == ("user:a",)

    def test_sources_lists_registered(self, tmp_path) -> None:
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "a.json").write_text(
            json.dumps({"on": "note.created", "enabled": True}), encoding="utf-8"
        )
        HookLoader(hooks).load_dir(d, source="user", approved=True)
        assert hooks.sources == ("user:a",)


class TestReloadService:
    """B1–B5:reload 服务级行为(不经 build_agent)。"""

    async def test_reload_loads_and_returns_shape(self, tmp_path) -> None:
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "note-watch.json",
                    {"on": "note.created", "description": "笔记新建", "enabled": True})
        _write_hook(hooks_dir, "lifecycle.json", {"on": "on_user_message", "enabled": True})
        out = reloader.reload()
        assert out["loaded"] == 2
        assert out["event_patterns"] == ["note.created"]  # 生命周期点不进订阅
        assert out["skipped"] == []
        assert reg.registered() == {"on_event": 1, "on_user_message": 1}
        assert "user:note-watch" in reg.sources

    async def test_reload_idempotent_no_duplicate(self, tmp_path) -> None:
        """先 load_dir(模拟启动装载)再 reload:先卸后装,不重复注册。"""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        HookLoader(reg).load_dir(hooks_dir, source="user", approved=True)
        out = reloader.reload()
        assert out["loaded"] == 1
        assert reg.registered() == {"on_event": 1}
        assert reg.event_patterns == ("note.created",)

    async def test_empty_dir_clears_user_hooks(self, tmp_path) -> None:
        """B3:文件清空后 reload → loaded=0,用户钩子与订阅清零,不炸。"""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        HookLoader(reg).load_dir(hooks_dir, source="user", approved=True)
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["loaded"] == 0
        assert out["event_patterns"] == []
        assert reg.registered() == {}

    async def test_missing_dir_succeeds_zero(self, tmp_path) -> None:
        """B3:目录不存在视为空,成功返回 loaded=0,不建目录不炸。"""
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        out = reloader.reload()
        assert out == {"loaded": 0, "event_patterns": [], "skipped": []}
        assert not hooks_dir.exists()

    async def test_bad_json_skipped_and_disclosed(self, tmp_path) -> None:
        """B4:坏 json 单文件跳过披露,其余文件照装(对标插件装载容错)。"""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "broken.json").write_text("{not json", encoding="utf-8")
        _write_hook(hooks_dir, "good.json", {"on": "note.created", "enabled": True})
        out = reloader.reload()
        assert out["loaded"] == 1
        assert len(out["skipped"]) == 1
        assert out["skipped"][0]["path"] == "broken.json"
        assert out["skipped"][0]["reason"]
        assert reg.registered() == {"on_event": 1}

    async def test_non_dict_json_skipped(self, tmp_path) -> None:
        """JSON 数组等非对象文件同样按坏文件跳过,不炸重载。"""
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "array.json").write_text("[1, 2]", encoding="utf-8")
        out = reloader.reload()
        assert out["loaded"] == 0
        assert [s["path"] for s in out["skipped"]] == ["array.json"]

    async def test_non_string_on_does_not_break_reload(self, tmp_path) -> None:
        """loader 对异常 on 值宽松(非串原样进 event_patterns):reload 全程不炸,
        new_ons 镜像 loader 不误撤;撤订阅排序 key=str 不因混类型崩。"""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "num.json").write_text(
            json.dumps({"on": 123, "enabled": True}), encoding="utf-8"
        )
        _write_hook(hooks_dir, "note.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        assert 123 in reg.event_patterns  # loader 原样记录,reload 不改写该语义
        (hooks_dir / "num.json").unlink()
        (hooks_dir / "note.json").unlink()
        reloader.reload()  # 撤订阅差集混含 123 与 note.created
        assert reg.event_patterns == ()

    async def test_disabled_file_not_loaded(self, tmp_path) -> None:
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "off.json", {"on": "note.created", "enabled": False})
        out = reloader.reload()
        assert out["loaded"] == 0
        assert reg.event_patterns == ()
        assert reg.registered() == {}

    async def test_sync_called_with_latest_patterns(self, tmp_path) -> None:
        """A2:reload 经注入的同一 sync 回调收敛订阅;注入时先同步基线。"""
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        seen: list[tuple[str, ...]] = []
        reloader.set_subscription_sync(seen.append)
        assert seen == [()]  # 注入即基线同步
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        assert seen[-1] == ("note.created",)

    async def test_lifecycle_hook_fires_after_reload(self, tmp_path, caplog) -> None:
        """A5:生命周期点 hook 重载后立即参与 fire;不进 event_patterns。"""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "life.json", {"on": "on_user_message", "enabled": True})
        reloader.reload()
        with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
            await reg.fire("on_user_message", content="hi")
        assert sum("life" in r.message for r in caplog.records) == 1


class TestSelectiveForget:
    """A3/A4/C3:撤订阅只摘用户侧,插件订阅不误撤(分层判定)。"""

    async def test_user_only_pattern_forgotten_after_delete(self, tmp_path) -> None:
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == []
        assert "note.created" not in reg.event_patterns

    async def test_pattern_kept_while_other_user_file_declares(self, tmp_path) -> None:
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        _write_hook(hooks_dir, "b.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == ["note.created"]  # b.json 仍声明

    async def test_pattern_kept_for_plugin_owner(self, tmp_path) -> None:
        """A4(owner 层):插件仍装载同 pattern 时,删用户文件不撤订阅。"""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        reg.record_event_pattern("note.created", source="plugin:ex:hooks/on-note.json")
        reg.register("on_event", lambda **kw: None, source="plugin:ex:hooks/on-note.json")
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == ["note.created"]  # 插件还在,订阅保留
        assert reg.registered() == {"on_event": 1}  # 剩的是插件的注册

    async def test_unload_only_user_prefix(self, tmp_path) -> None:
        """A3:热卸只摘 user: 前缀,插件及其它前缀注册不动。"""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        reg.register("post_tool", lambda **kw: None, source="plugin:ex:h")
        reg.register("post_tool", lambda **kw: None, source="local")
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        reloader.reload()
        assert reg.registered() == {"post_tool": 2}  # 插件与 local 注册都在

    async def test_plugin_backup_keeps_pattern(self, tmp_path) -> None:
        """A4(插件兜底层):owner 无插件记录但已批准插件仍需要 → 保留订阅。"""
        plugins = SimpleNamespace(pattern_still_wanted=lambda pattern: True)
        reloader, hooks_dir, _reg = _reloader(tmp_path, plugins=plugins)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == ["note.created"]

    async def test_declared_plugin_backup_not_enough_when_nobody_needs(self, tmp_path) -> None:
        """兜底判定为 False 且无 owner → 撤;不给悬空订阅留死账。"""
        plugins = SimpleNamespace(pattern_still_wanted=lambda pattern: False)
        reloader, hooks_dir, _reg = _reloader(tmp_path, plugins=plugins)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        assert reloader.reload()["event_patterns"] == []


class TestListService:
    """B5:list_user_hooks 只读列举。"""

    async def test_list_shape_and_loaded_flag(self, tmp_path) -> None:
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "on.json", {"on": "note.created", "description": "开", "enabled": True})
        _write_hook(hooks_dir, "off.json", {"on": "note.deleted", "enabled": False})
        reloader.reload()  # 只装 on.json
        items = reloader.list()
        by_name = {i["path"]: i for i in items}
        assert set(by_name) == {"on.json", "off.json"}
        assert by_name["on.json"]["on"] == "note.created"
        assert by_name["on.json"]["enabled"] is True
        assert by_name["on.json"]["description"] == "开"
        assert by_name["on.json"]["loaded"] is True
        assert by_name["off.json"]["loaded"] is False

    async def test_list_bad_file_zeroed(self, tmp_path) -> None:
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "bad.json").write_text("{oops", encoding="utf-8")
        (items,) = reloader.list()
        assert items["path"] == "bad.json"
        assert items["on"] == "" and items["enabled"] is False and items["loaded"] is False

    async def test_list_missing_dir_empty(self, tmp_path) -> None:
        reloader, _hooks_dir, _reg = _reloader(tmp_path)
        assert reloader.list() == []


class TestCapabilityContract:
    """B1/B2/B6/E1:能力面契约(经 build_agent 全家桶)。"""

    def _build(self, tmp_path):
        return build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM()
        )

    async def test_reload_contract_shape(self, tmp_path) -> None:
        app = self._build(tmp_path)
        try:
            _write_hook(tmp_path / "ws" / "hooks", "a.json",
                        {"on": "note.created", "description": "u", "enabled": True})
            out = await execute(app.registry, "reload_user_hooks", USER_CTX, {})
            assert out == {"loaded": 1, "event_patterns": ["note.created"], "skipped": []}
            assert "note.created" in app.loop.patterns  # 订阅同步已到位
        finally:
            app.memory.close()

    async def test_agent_actor_rejected(self, tmp_path) -> None:
        app = self._build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "reload_user_hooks", AGENT_CTX, {})
            assert exc.value.body.code == "AGENT.FORBIDDEN"
        finally:
            app.memory.close()

    async def test_no_actor_rejected(self, tmp_path) -> None:
        app = self._build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "reload_user_hooks", None, {})
            assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"
        finally:
            app.memory.close()

    async def test_no_path_parameter_accepted(self, tmp_path) -> None:
        """E1:能力无路径参数;传 path 之类入参被框架拒(TypeError),
        不存在「任意路径装载」通道。"""
        app = self._build(tmp_path)
        try:
            params = inspect_capability_params(app, "reload_user_hooks")
            assert params == set()  # 除 _actor 注入外无任何入参
            with pytest.raises(TypeError):
                await execute(app.registry, "reload_user_hooks", USER_CTX,
                              {"path": str(tmp_path / "elsewhere")})
        finally:
            app.memory.close()

    async def test_list_user_hooks_contract(self, tmp_path) -> None:
        _write_hook(tmp_path / "ws" / "hooks", "a.json",
                    {"on": "note.created", "description": "u", "enabled": True})
        app = self._build(tmp_path)
        try:
            out = await execute(app.registry, "list_user_hooks", USER_CTX, {})
            assert out == {"items": [{
                "path": "a.json", "on": "note.created", "enabled": True,
                "description": "u", "loaded": True,
            }]}
        finally:
            app.memory.close()


def inspect_capability_params(app, name: str) -> set[str]:
    """capability handler 的显式入参名(排除 _actor 注入)。"""
    import inspect

    handler = app.registry.get(name).handler
    return {p for p in inspect.signature(handler).parameters if p != "_actor"}


# ---- C1/C2/C3:live loop 集成(build_agent + 真 EventLoop,免重启生效) ----


async def _run_loop_task(loop: EventLoop):
    task = asyncio.create_task(loop.run())
    for _ in range(100):  # run() 先补读再 subscribe;等装配完成
        if loop._sub is not None:
            break
        await asyncio.sleep(0)
    await asyncio.sleep(0)  # 确保已阻塞在 sub.get
    return task


class TestLiveLoopIntegration:
    """同一进程不重建 app:写文件 → reload → publish 触发;删文件 → reload 即退。"""

    async def _app_with_live_loop(self, tmp_path):
        bus = EventBus(EventLog(tmp_path / "events.db"))
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
            plugins_dir=tmp_path / "plugins", bus=bus,
        )
        task = await _run_loop_task(app.loop)
        return app, bus, task

    async def test_write_reload_publish_triggers(self, tmp_path, caplog) -> None:
        """C2:reload 后同进程 publish(note.created)→ 用户 hook 真触发。"""
        app, bus, task = await self._app_with_live_loop(tmp_path)
        try:
            assert "note.created" not in app.loop.patterns  # reload 前未订阅
            _write_hook(tmp_path / "ws" / "hooks", "u.json",
                        {"on": "note.created", "description": "用户观察", "enabled": True})
            out = await execute(app.registry, "reload_user_hooks", USER_CTX, {})
            assert out["loaded"] == 1
            assert "note.created" in app.loop.patterns  # 免重启即订
            with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
                await bus.publish(Event(type="note.created", actor=LOCAL_USER, payload={}))
                await asyncio.sleep(0)
            assert sum("用户观察" in r.message for r in caplog.records) == 1
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()  # build_agent 内部自建的空 EventLog(owns_log=False)
            app.memory.close()

    async def test_delete_reload_stops_trigger(self, tmp_path, caplog) -> None:
        """C3(无插件):删文件 → reload → 再 publish 不再触发,订阅退出。"""
        hooks_dir = tmp_path / "ws" / "hooks"
        _write_hook(hooks_dir, "u.json",
                    {"on": "note.created", "description": "用户观察", "enabled": True})
        app, bus, task = await self._app_with_live_loop(tmp_path)
        try:
            assert "note.created" in app.loop.patterns  # 启动装载已订
            (hooks_dir / "u.json").unlink()
            await execute(app.registry, "reload_user_hooks", USER_CTX, {})
            assert "note.created" not in app.loop.patterns  # 撤订阅
            with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
                await bus.publish(Event(type="note.created", actor=LOCAL_USER, payload={}))
                await asyncio.sleep(0)
            assert caplog.records == []  # 不再触发
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()
            app.memory.close()

    async def test_plugin_subscription_survives_user_reload(self, tmp_path, caplog) -> None:
        """C1/A4/C3(有插件):插件批准 note.created;用户 hook 同 pattern 增删
        reload 均不动插件——计数、source、订阅全保留;直到插件撤销才退订。"""
        _make_plugin(tmp_path / "plugins", "ex")
        app, _bus, task = await self._app_with_live_loop(tmp_path)
        try:
            # 批准插件 → 订阅在,插件 hook 在
            await execute(app.registry, "set_plugin_approval", USER_CTX,
                          {"name": "ex", "approved": True})
            assert "note.created" in app.loop.patterns
            plugin_sources = [s for s in app.hooks.sources if s.startswith("plugin:")]
            assert plugin_sources == ["plugin:ex:on-note"]  # source 用文件主干
            # 用户写同 pattern hook → reload:插件注册与订阅不受影响
            _write_hook(tmp_path / "ws" / "hooks", "u.json",
                        {"on": "note.created", "description": "用户观察", "enabled": True})
            await execute(app.registry, "reload_user_hooks", USER_CTX, {})
            assert app.hooks.registered() == {"on_event": 2}
            assert "note.created" in app.loop.patterns
            assert [s for s in app.hooks.sources if s.startswith("plugin:")] == plugin_sources
            # 删用户文件 → reload:pattern 仍因插件保留
            (tmp_path / "ws" / "hooks" / "u.json").unlink()
            await execute(app.registry, "reload_user_hooks", USER_CTX, {})
            assert app.hooks.registered() == {"on_event": 1}
            assert "note.created" in app.loop.patterns
            # 撤销插件:无人需要,pattern 才退出
            await execute(app.registry, "set_plugin_approval", USER_CTX,
                          {"name": "ex", "approved": False})
            assert "note.created" not in app.loop.patterns
            assert caplog.records == []  # 本用例未 publish,以上全为状态断言
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()
            app.memory.close()
