"""插件发现 / 整包批准 / 装载测试(phase-72,§9.13)。

夹具全部用 tmp 插件目录(经 build_agent 的 plugins_dir 注入),不依赖仓库
plugins/_example 的内容;默认不装载的既有语义由 test_skills/test_hooks 锁定。
"""

import json
import shutil
from pathlib import Path

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError

from agent.llm import FakeLLM
from agent.main import build_agent

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


def make_plugin(
    root: Path,
    name: str = "example",
    *,
    version: str = "0.1.0",
    description: str = "测试插件",
    skills: tuple[str, ...] = ("skills/daily-note",),
    hooks: tuple[str, ...] = ("hooks/on-note-created.json",),
    mcp: str | None = "mcp.json",
    hook_enabled: bool = False,
    raw_manifest: dict | None = None,
) -> Path:
    """造一个声明式插件目录;字段可关,mcp=None 表示不含 MCP 配置。"""
    d = root / name
    d.mkdir(parents=True)
    manifest = raw_manifest if raw_manifest is not None else {
        "name": name,
        "version": version,
        "description": description,
        "permissions": {"scopes": ["notes.write"], "network": "off", "fs": "none"},
        "contains": {
            "skills": list(skills),
            "hooks": list(hooks),
            "mcp": mcp,
        },
    }
    (d / "plugin.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    for skill in skills:
        skill_dir = d / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"# {skill_dir.name}\n\n测试用 skill 全文。\n", encoding="utf-8"
        )
    for hook in hooks:
        hook_path = d / hook
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(
            json.dumps({"on": "note.created", "description": "测试 hook",
                        "enabled": hook_enabled}),
            encoding="utf-8",
        )
    if mcp:
        (d / mcp).write_text(
            json.dumps({"servers": {
                f"{name}-search": {"command": "npx", "args": ["-y", "x"]},
            }}),
            encoding="utf-8",
        )
    return d


def build(tmp_path, **overrides):
    """build_agent:插件根固定 tmp_path/plugins,其余可覆盖。"""
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir(exist_ok=True)
    app = build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
        plugins_dir=plugins_root, **overrides,
    )
    return app


@pytest.fixture()
def app(tmp_path):
    a = build(tmp_path)
    yield a
    a.memory.close()


async def _approve(app, name: str = "example") -> dict:
    return await execute(
        app.registry, "set_plugin_approval", USER_CTX, {"name": name, "approved": True}
    )


class TestDiscover:
    """A1/A2:发现、坏清单跳过、`_` 前缀可见但不装载。"""

    def test_underscore_prefix_listed(self, tmp_path) -> None:
        """`_` 前缀目录照常 list 可见(选型:list 可见,未批准不装载)。"""
        make_plugin(tmp_path / "plugins", "_example")
        app = build(tmp_path)
        try:
            names = [m.name for m in app.plugins.manifests()]
            assert "_example" in names
            assert [i["name"] for i in app.plugins.list()] == ["_example"]
        finally:
            app.memory.close()

    def test_bad_or_missing_manifest_skipped(self, tmp_path) -> None:
        """坏 JSON / 缺 name / 没有 plugin.json 的目录跳过,不炸 boot。"""
        root = tmp_path / "plugins"
        root.mkdir()
        (root / "broken").mkdir()
        (root / "broken" / "plugin.json").write_text("{不是json", encoding="utf-8")
        (root / "no-name").mkdir()
        (root / "no-name" / "plugin.json").write_text('{"version": "1.0"}', encoding="utf-8")
        (root / "not-json").mkdir()
        (root / "plain").mkdir()  # 连清单都没有
        app = build(tmp_path)
        try:
            assert app.plugins.manifests() == []
        finally:
            app.memory.close()

    def test_missing_optional_keys_defaulted(self, tmp_path) -> None:
        """只有 name 也算合法清单:version/description/permissions/contains 给默认。"""
        make_plugin(tmp_path / "plugins", "minimal", raw_manifest={"name": "minimal"})
        app = build(tmp_path)
        try:
            (item,) = app.plugins.list()
            assert item["name"] == "minimal"
            assert item["version"] == "" and item["description"] == ""
            assert item["permissions"] == {"scopes": [], "network": "", "fs": ""}
            assert item["contains"] == {"skills": 0, "hooks": 0, "mcp": False}
        finally:
            app.memory.close()

    def test_list_shape_stable(self, app, tmp_path) -> None:
        """A3:list_plugins 契约形状(permissions 归一 + contains 计数 + path)。"""
        make_plugin(tmp_path / "plugins", "example")
        assert app.plugins.list() == [{
            "name": "example",
            "version": "0.1.0",
            "description": "测试插件",
            "approved": False,
            "permissions": {"scopes": ["notes.write"], "network": "off", "fs": "none"},
            "contains": {"skills": 1, "hooks": 1, "mcp": True},
            "path": "example",
        }]

    async def test_capability_list_plugins_shape(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        out = await execute(app.registry, "list_plugins", USER_CTX, {})
        assert out == {"items": app.plugins.list()}
        assert out["items"][0]["name"] == "example"


class TestPathJail:
    """C4:contains 相对路径不得逃出插件目录。"""

    def test_escape_and_absolute_rejected(self, app, tmp_path) -> None:
        """../ 与绝对路径的 contains 条目:计数为 0,不进 list。"""
        root = tmp_path / "plugins"
        make_plugin(root, "escapee", skills=("../outside/skill-a",))
        # 逃逸目标确实存在于插件目录之外
        outside = tmp_path / "outside" / "skill-a"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_text("# outside\n", encoding="utf-8")
        make_plugin(root, "abs", skills=(str(tmp_path / "evil" / "skill-b"),),
                    mcp=None, hooks=())
        items = {i["name"]: i for i in app.plugins.list()}
        assert items["escapee"]["contains"]["skills"] == 0
        assert items["abs"]["contains"]["skills"] == 0

    async def test_escape_not_loaded_after_approve(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "escapee", skills=("../outside/skill-a",))
        outside = tmp_path / "outside" / "skill-a"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_text("# outside\n", encoding="utf-8")
        app = build(tmp_path)
        try:
            out = await _approve(app, "escapee")
            assert out["loaded"]["skills"] == []  # 逃逸条目不装载
            assert "skill-a" not in [e["name"] for e in app.skills.index()]
        finally:
            app.memory.close()


class TestApproval:
    """B1/B4:capability 面、USER-only、granularity 本刀只做 bundle。"""

    async def test_approve_returns_contract_shape(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        out = await _approve(app)
        assert out == {
            "name": "example",
            "approved": True,
            "loaded": {"skills": ["daily-note"], "hooks": 0,
                       "mcp_registered": 1, "mcp_skipped": False},
        }

    async def test_agent_actor_rejected(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "set_plugin_approval", AGENT_CTX,
                          {"name": "example", "approved": True})
        assert exc.value.body.code == "AGENT.FORBIDDEN"
        assert app.settings.get("agent.plugins.approved") == []

    async def test_no_actor_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "set_plugin_approval", None,
                          {"name": "example", "approved": True})
        assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"

    async def test_granularity_item_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "set_plugin_approval", USER_CTX,
                          {"name": "example", "approved": True, "granularity": "item"})
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_unknown_plugin_not_found(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _approve(app, "ghost")
        assert exc.value.body.code == "AGENT.NOT_FOUND"


class TestPersistAndReload:
    """B2/B3/C3:名单持久化、重启装载、撤销热卸。"""

    async def test_approved_survives_rebuild(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app1 = build(tmp_path)
        try:
            await _approve(app1)
            assert app1.settings.get("agent.plugins.approved") == ["example"]
            assert "daily-note" in [e["name"] for e in app1.skills.index()]
            assert app1.hooks.registered() == {"on_event": 1}
        finally:
            app1.close()
        app2 = build(tmp_path)  # 重启:同 data_dir,读持久化名单
        try:
            assert "daily-note" in [e["name"] for e in app2.skills.index()]
            assert app2.hooks.registered() == {"on_event": 1}
            assert "note.created" in app2.loop.patterns
        finally:
            app2.close()

    async def test_unapproved_default_not_loaded(self, app, tmp_path) -> None:
        """未批准(默认):skill 不在索引、hook 不 load、MCP 不登记(C3 基线)。"""
        make_plugin(tmp_path / "plugins", "example", hook_enabled=True)
        assert "daily-note" not in [e["name"] for e in app.skills.index()]
        assert app.hooks.registered() == {}
        assert await execute(app.registry, "list_mcp_servers", USER_CTX, {}) == []

    async def test_unapprove_hot_unloads(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app = build(tmp_path)
        try:
            await _approve(app)
            assert "daily-note" in [e["name"] for e in app.skills.index()]
            out = await execute(app.registry, "set_plugin_approval", USER_CTX,
                                {"name": "example", "approved": False})
            assert out["approved"] is False
            assert out["unloaded"] == {"skills": 1, "hooks": 1}
            # 热卸:list 立即消失、hook 注册与事件订阅一并撤
            assert "daily-note" not in [e["name"] for e in app.skills.index()]
            assert app.hooks.registered() == {}
            assert "note.created" not in app.loop.patterns
            assert app.settings.get("agent.plugins.approved") == []
            assert out["loaded"] == {"skills": [], "hooks": 0,
                                     "mcp_registered": 0, "mcp_skipped": False}
        finally:
            app.memory.close()

    async def test_unapprove_survives_rebuild(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app1 = build(tmp_path)
        try:
            await _approve(app1)
        finally:
            app1.close()
        app2 = build(tmp_path)
        try:
            await execute(app2.registry, "set_plugin_approval", USER_CTX,
                          {"name": "example", "approved": False})
        finally:
            app2.close()
        app3 = build(tmp_path)
        try:
            assert "daily-note" not in [e["name"] for e in app3.skills.index()]
            assert app3.settings.get("agent.plugins.approved") == []
        finally:
            app3.close()

    async def test_unapprove_purges_stale_entry(self, tmp_path) -> None:
        """名单残留死条目(插件目录已被删)撤销时清名单,不抛 NOT_FOUND。"""
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app = build(tmp_path)
        try:
            await _approve(app)
            assert app.settings.get("agent.plugins.approved") == ["example"]
            shutil.rmtree(root / "example")
            out = await execute(app.registry, "set_plugin_approval", USER_CTX,
                                {"name": "example", "approved": False})
            assert out["approved"] is False
            assert out["unloaded"] == {"skills": 0, "hooks": 0}  # 清单不在:跳过热卸
            assert app.settings.get("agent.plugins.approved") == []
        finally:
            app.close()

    async def test_unload_keeps_pattern_declared_by_other(self, tmp_path) -> None:
        """两个插件声明同一事件 pattern:撤一个,另一个的 hook 注册与声明保留。"""
        root = tmp_path / "plugins"
        make_plugin(root, "alpha", hook_enabled=True)
        make_plugin(root, "beta", hook_enabled=True)
        app = build(tmp_path)
        try:
            await _approve(app, "alpha")
            await _approve(app, "beta")
            assert app.hooks.registered() == {"on_event": 2}
            await execute(app.registry, "set_plugin_approval", USER_CTX,
                          {"name": "alpha", "approved": False})
            assert app.hooks.registered() == {"on_event": 1}  # beta 的 hook 仍在
            assert app.hooks.event_patterns == ("note.created",)  # beta 的声明未被误撤
        finally:
            app.close()


class TestSkillHookLoad:
    """C1/C2:批准后 skill 进索引可读全文;hook 进 registry;未批准不 load。"""

    async def test_read_skill_full_text(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        await _approve(app)
        doc = await execute(app.registry, "read_skill", USER_CTX, {"name": "daily-note"})
        assert doc["name"] == "daily-note" and "测试用 skill 全文" in doc["text"]

    async def test_enabled_hook_loaded_disabled_not(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example", hook_enabled=False)
        out = await _approve(app)
        assert out["loaded"]["hooks"] == 0  # enabled=false 的 hook 装载计数为 0
        assert app.hooks.registered() == {}

    async def test_repeated_approve_idempotent(self, app, tmp_path) -> None:
        """重复批准(重试/启动后再次批准):skill root 去重、hook 不重复注册、订阅不翻倍。

        注:运行期装载不实时改 bus 订阅快照(loop.patterns 装配期定死,重启才进),
        故断言 hooks.event_patterns(registry 实时层)而非 loop.patterns。
        """
        make_plugin(tmp_path / "plugins", "example", hook_enabled=True)
        await _approve(app)
        await _approve(app)
        names = [e["name"] for e in app.skills.index()]
        assert names.count("daily-note") == 1
        assert app.hooks.registered() == {"on_event": 1}
        assert app.hooks.event_patterns.count("note.created") == 1


class TestMcpRegistration:
    """D1/D2:MCP 薄接入——登记待批准条目,不自动批准工具。"""

    async def test_servers_registered_pending_approval(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        await _approve(app)
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert [s["id"] for s in servers] == ["example-search"]
        assert servers[0]["approved"] == []  # 只登记,不批准工具
        tools = {t["name"] for t in await execute(app.registry, "list_tools", USER_CTX, {})}
        assert not [n for n in tools if n.startswith("mcp__")]

    async def test_missing_mcp_json_skipped(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example", mcp=None)
        out = await _approve(app)
        assert out["loaded"]["mcp_registered"] == 0
        assert out["loaded"]["mcp_skipped"] is True

    async def test_bad_or_empty_mcp_json_skipped(self, app, tmp_path) -> None:
        root = tmp_path / "plugins"
        d = make_plugin(root, "example")
        (d / "mcp.json").write_text("{坏", encoding="utf-8")
        out = await _approve(app)
        assert out["loaded"]["mcp_skipped"] is True
        # 改成空 servers 后再次批准:mcp 步骤仍按跳过处理
        (d / "mcp.json").write_text('{"servers": {}}', encoding="utf-8")
        out2 = await _approve(app)
        assert out2["loaded"]["mcp_registered"] == 0
        assert out2["loaded"]["mcp_skipped"] is True

    async def test_invalid_server_entry_skipped_without_fail(self, app, tmp_path) -> None:
        """坏 server 条目(缺 command)跳过,skill/hook 批准仍成功。"""
        root = tmp_path / "plugins"
        d = make_plugin(root, "example")
        (d / "mcp.json").write_text(
            json.dumps({"servers": {"bad-srv": {"command": ""}}}), encoding="utf-8"
        )
        out = await _approve(app)
        assert out["loaded"]["mcp_registered"] == 0
        assert out["loaded"]["mcp_skipped"] is False  # 文件可解析:只是条目被跳过
        assert out["loaded"]["skills"] == ["daily-note"]

    async def test_existing_server_id_not_overwritten(self, app, tmp_path) -> None:
        """用户手动加过同 id:跳过不覆盖,原批准状态保持。"""
        make_plugin(tmp_path / "plugins", "example")
        await execute(app.registry, "add_mcp_server", USER_CTX,
                      {"id": "example-search", "kind": "stdio", "command": "npx"})
        await execute(app.registry, "approve_mcp_tools", USER_CTX,
                      {"id": "example-search", "names": ["*"]})
        out = await _approve(app)
        assert out["loaded"]["mcp_registered"] == 0
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert servers[0]["approved"] == ["*"]  # 原整包批准未被插件批准动过
