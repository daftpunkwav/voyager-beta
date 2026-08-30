"""外接 MCP 全链路测试(phase-11b,§9.13):连接层全走 Fake(内存 dict,无进程无网)。

覆盖:add → preview → 未批准不可见 → 整包/逐项批准挂载 → Toolbelt.call 到 Fake
返回值 → remove 卸载 → 重启(mcp.start)自动重连 → 默认空池不混领域桥 → 非法入参。
"""

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent

USER_CTX = ActorContext(actor=LOCAL_USER)


class FakeSession:
    """内存 MCP server:固定两个远端工具,记录调用。"""

    TOOLS = [
        {"name": "search", "description": "搜索", "schema": {"type": "object"}},
        {"name": "fetch", "description": "抓取远端页面"},  # 无 schema → 兜底 schema
    ]

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_remote_tools(self) -> list[dict]:
        return [dict(t) for t in self.TOOLS]

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return f"fake:{name}:{arguments.get('q', '')}"

    async def aclose(self) -> None:
        self.closed = True


def fake_connect(sessions: dict[str, FakeSession], fail_ids: frozenset[str] = frozenset()):
    """池的 connect 注入口:按 id 建 Fake session;fail_ids 里的 id 连接失败。"""

    async def connect(cfg: dict) -> FakeSession:
        if cfg["id"] in fail_ids:
            raise RuntimeError("连接被拒(测试模拟)")
        session = FakeSession()
        sessions[cfg["id"]] = session
        return session

    return connect


@pytest.fixture()
def app(tmp_path):
    sessions: dict[str, FakeSession] = {}
    app = build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
        mcp_connect=fake_connect(sessions),
    )
    app.sessions = sessions  # 测试句柄:断言 Fake 收到的调用
    yield app
    app.memory.close()


async def _add(app, **overrides) -> dict:
    args = {"id": "demo", "kind": "stdio", "command": "npx", "args": ["-y", "x"],
            "approval": "item"}
    args.update(overrides)
    return await execute(app.registry, "add_mcp_server", USER_CTX, args)


async def _list_tools(app) -> set[str]:
    return {t["name"] for t in await execute(app.registry, "list_tools", USER_CTX, {})}


class TestAddAndPreview:
    async def test_add_previews_but_not_approved_hidden(self, app) -> None:
        """add 成功且能列出远端工具;未批准时 list_tools / 名册都没有 mcp__*。"""
        result = await _add(app)
        assert result["ok"] is True and result["connected"] is True
        assert {t["name"] for t in result["preview"]} == {"search", "fetch"}
        assert "mcp__demo__search" not in await _list_tools(app)
        assert not [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__")]

    async def test_add_keeps_config_when_connect_fails(self, tmp_path) -> None:
        """连接失败仍保留配置:返回 connected=False + 可读 error,配置可再试。"""
        sessions: dict[str, FakeSession] = {}
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
            mcp_connect=fake_connect(sessions, fail_ids=frozenset({"bad"})),
        )
        try:
            result = await execute(
                app.registry, "add_mcp_server", USER_CTX,
                {"id": "bad", "kind": "stdio", "command": "npx"},
            )
            assert result["ok"] is True and result["connected"] is False
            assert "连接被拒" in result["error"] and result["preview"] == []
            state = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
            assert [s["id"] for s in state] == ["bad"]
        finally:
            app.memory.close()

    async def test_add_duplicate_id_conflict(self, app) -> None:
        await _add(app)
        with pytest.raises(ServiceError) as exc:
            await _add(app)
        assert exc.value.body.code.endswith("CONFLICT")


class TestApproveAndMount:
    async def test_package_approve_mounts_and_callable(self, app) -> None:
        """整包批准(names=['*'])→ 名册出现 mcp__*,Toolbelt.call 调到 Fake 返回值。"""
        await _add(app)
        result = await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["*"]}
        )
        assert result["approved"] == ["*"]
        assert set(result["mounted"]) == {"mcp__demo__search", "mcp__demo__fetch"}
        names = await _list_tools(app)
        assert {"mcp__demo__search", "mcp__demo__fetch"} <= names
        out = await app.spawner._toolbelt.call(
            ToolCall(id="1", name="mcp__demo__search", arguments={"q": "mcp"})
        )
        assert out == "fake:search:mcp"
        assert app.sessions["demo"].calls == [("search", {"q": "mcp"})]

    async def test_item_approve_only_selected(self, app) -> None:
        """逐项批准只挂点名的;累积批准不撤销先前项。"""
        await _add(app)
        result = await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["search"]}
        )
        assert result["mounted"] == ["mcp__demo__search"]
        assert "mcp__demo__search" in await _list_tools(app)
        assert "mcp__demo__fetch" not in await _list_tools(app)
        # 再批准 fetch:两项都在,先批的 search 不被撤销
        result = await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["fetch"]}
        )
        assert set(result["mounted"]) == {"mcp__demo__search", "mcp__demo__fetch"}

    async def test_item_approve_unknown_name_rejected(self, app) -> None:
        await _add(app)
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry, "approve_mcp_tools", USER_CTX,
                {"id": "demo", "names": ["不存在的工具"]},
            )
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_item_approve_requires_names(self, app) -> None:
        await _add(app)
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo"})
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_remount_replaces_stale_names(self, app) -> None:
        """重挂(整包)先卸旧挂:名册无残名,不重复。"""
        await _add(app)
        await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["search"]}
        )
        await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["*"]}
        )
        mcp_names = [n for n in await _list_tools(app) if n.startswith("mcp__")]
        assert sorted(mcp_names) == ["mcp__demo__fetch", "mcp__demo__search"]


class TestRemove:
    async def test_remove_unmounts_and_forgets(self, app) -> None:
        await _add(app)
        await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["*"]}
        )
        session = app.sessions["demo"]
        await execute(app.registry, "remove_mcp_server", USER_CTX, {"id": "demo"})
        assert not [n for n in await _list_tools(app) if n.startswith("mcp__")]
        out = await app.spawner._toolbelt.call(
            ToolCall(id="2", name="mcp__demo__search", arguments={})
        )
        assert "未知工具" in out
        state = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert state == []
        assert session.closed  # 会话已断开

    async def test_remove_unknown_not_found(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "remove_mcp_server", USER_CTX, {"id": "ghost"})
        assert exc.value.body.code.endswith("NOT_FOUND")


class TestRestart:
    async def test_start_reconnects_approved(self, tmp_path) -> None:
        """settings 预写 approved=['*'] → 新进程 build_agent + mcp.start() 自动挂载。"""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        cfg = {
            "id": "demo", "name": "demo", "kind": "stdio", "command": "npx",
            "args": [], "url": "", "approval": "package", "approved": ["*"],
            "enabled": True,
        }
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
            settings_store=shared, mcp_connect=fake_connect(sessions),
        )
        await shared.set("agent.mcp.servers", [cfg], LOCAL_USER)  # build 已注册该 key
        try:
            assert not [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__")]
            await app.mcp.start()
            assert "mcp__demo__search" in app.spawner._toolbelt.names()
            # 幂等:重复 start 不炸不重复
            await app.mcp.start()
            names = [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__")]
            assert len(names) == 2
        finally:
            app.close()
            shared.close()

    async def test_preview_remounts_after_start_failure(self, tmp_path) -> None:
        """启动连不上 → 修好后 preview 会按已批准重挂,不必再点批准。"""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        fail_ids = {"broken"}

        async def flaky_connect(cfg: dict) -> FakeSession:
            if cfg["id"] in fail_ids:
                raise RuntimeError("连接被拒(测试模拟)")
            session = FakeSession()
            sessions[cfg["id"]] = session
            return session

        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
            settings_store=shared, mcp_connect=flaky_connect,
        )
        await shared.set("agent.mcp.servers", [{
            "id": "broken", "name": "b", "kind": "stdio", "command": "npx",
            "args": [], "url": "", "approval": "package", "approved": ["*"],
            "enabled": True,
        }], LOCAL_USER)
        try:
            await app.mcp.start()
            assert "mcp__broken__search" not in app.spawner._toolbelt.names()
            fail_ids.clear()
            await execute(app.registry, "preview_mcp_tools", USER_CTX, {"id": "broken"})
            assert "mcp__broken__search" in app.spawner._toolbelt.names()
        finally:
            app.close()
            shared.close()

    async def test_start_skips_unapproved_and_records_failure(self, tmp_path) -> None:
        """enabled 但未批准的不连;批准但连不上的记条目 error,不挡启动。"""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
            settings_store=shared,
            mcp_connect=fake_connect(sessions, fail_ids=frozenset({"broken"})),
        )
        await shared.set("agent.mcp.servers", [
            {"id": "draft", "name": "d", "kind": "stdio", "command": "npx",
             "args": [], "url": "", "approval": "item", "approved": [], "enabled": True},
            {"id": "broken", "name": "b", "kind": "stdio", "command": "npx",
             "args": [], "url": "", "approval": "package", "approved": ["*"], "enabled": True},
        ], LOCAL_USER)
        try:
            await app.mcp.start()
            assert "draft" not in sessions  # 未批准不连
            state = {s["id"]: s for s in app.mcp.list_state()}
            assert state["draft"]["connected"] is False
            assert state["broken"]["connected"] is False
            assert "连接被拒" in state["broken"]["error"]
        finally:
            app.memory.close()
            shared.close()


class TestDefaultEmpty:
    async def test_default_pool_empty_no_domain_bridge(self, tmp_path) -> None:
        """默认装配(不 start、无配置)池仍空;领域桥不经 MCP 名义出现。"""
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(),
        )
        try:
            assert app.mcp.list_state() == []
            names = app.spawner._toolbelt.names()
            assert not [n for n in names if n.startswith("mcp__")]
        finally:
            app.memory.close()


class TestInvalidInput:
    async def test_bad_id_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _add(app, id="Bad_ID")
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_file_url_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _add(app, id="u1", kind="url", url="file:///etc/passwd")
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_empty_command_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _add(app, id="s1", kind="stdio", command="  ")
        assert exc.value.body.code.endswith("INVALID_INPUT")


class TestDomains:
    def test_mcp_domain_activatable(self) -> None:
        """DOMAINS 含 mcp:Lucien 能 activate_tools(domain='mcp') 看见批准后的工具。"""
        from agent.tools.activate import CORE_TOOLS, DOMAINS

        assert "mcp" in DOMAINS
        assert "load_skill" in CORE_TOOLS  # 不许移出 CORE
        assert not [n for n in CORE_TOOLS if n.startswith("mcp__")]
