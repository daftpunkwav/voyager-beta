"""agent 能力注册表测试(§5/铁律 4):agent 的能力经 capability 框架与用户同权调用。"""

import asyncio

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError

from agent.llm import FakeLLM
from agent.main import build_agent

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    yield app
    app.memory.close()


class TestSettingsParity:
    async def test_get_settings_lists_schema(self, app) -> None:
        schema = await execute(app.registry, "get_settings", USER_CTX, {})
        keys = {s["key"] for s in schema}
        assert {"agent.rounds.max", "agent.style", "agent.arbiter.mode"} <= keys

    async def test_agent_can_change_setting_like_user(self, app) -> None:
        """parity:用户能改的设置 agent 也能改(非 secret),_actor 注入调用者。"""
        result = await execute(
            app.registry, "set_setting", AGENT_CTX, {"key": "agent.style", "value": "毒舌"}
        )
        assert result["ok"] is True
        assert app.settings.get("agent.style") == "毒舌"

    async def test_unknown_setting_rejected(self, app) -> None:
        with pytest.raises(ServiceError):
            await execute(
                app.registry, "set_setting", USER_CTX, {"key": "agent.不存在", "value": 1}
            )

    async def test_no_actor_auth_required(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "get_settings", None, {})
        assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"


class TestSurface:
    async def test_list_skills_and_read(self, app) -> None:
        index = await execute(app.registry, "list_skills", USER_CTX, {})
        names = {s["name"] for s in index}
        assert "explore-repo" in names  # 内置 skill 入库
        doc = await execute(
            app.registry, "read_skill", USER_CTX, {"name": "explore-repo"}
        )
        assert doc["name"] == "explore-repo" and doc["text"]

    async def test_report_page_context(self, app) -> None:
        await execute(
            app.registry,
            "report_page_context",
            USER_CTX,
            {"page": "notes", "summary": "36 条笔记", "counts": {"notes": 36}},
        )
        assert app.pages.current().page == "notes"
        assert "notes=36" in app.pages.render()

    async def test_answer_question_roundtrip(self, app) -> None:
        from agent.tools.ask_user import Question

        task = asyncio.create_task(app.asker.ask(Question(prompt="继续吗?")))
        await asyncio.sleep(0.01)
        qid = next(iter(app.asker._pending))  # 测试取等待中的问题 id
        out = await execute(
            app.registry,
            "answer_question",
            USER_CTX,
            {"question_id": qid, "value": True},
        )
        assert out["matched"] is True
        assert await task is True

    async def test_list_subagents_shape(self, app) -> None:
        out = await execute(app.registry, "list_subagents", USER_CTX, {})
        assert set(out) == {"definitions", "running"}
        assert isinstance(out["definitions"], list)
