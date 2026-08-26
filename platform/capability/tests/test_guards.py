"""守卫测试:鉴权、配额、审计、长任务约定。"""

from dataclasses import dataclass

import pytest
from platform_actor import ActorContext
from platform_capability import (
    CostQuota,
    InMemoryAuditSink,
    Registry,
    capability,
    execute,
    summarize_args,
)
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, JobRef, ServiceError


@dataclass
class _In:
    text: str
    api_key: str = ""


def _registry(long_running: bool = False) -> Registry:
    reg = Registry("notes")

    @capability(
        reg,
        name="do_thing",
        description="测试能力",
        input_model=_In,
        cost=5,
        scopes=("notes.write",),
        long_running=long_running,
    )
    async def do_thing(data: _In):
        if long_running:
            return JobRef(job_id="j-1")
        return {"ok": data.text}

    return reg


USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(
    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=("notes.write",))
)
STRANGER_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.other", scopes=()))


class TestAuth:
    async def test_user_always_allowed(self) -> None:
        assert await execute(_registry(), "do_thing", USER_CTX, {"text": "x"}) == {"ok": "x"}

    async def test_agent_with_scope_allowed(self) -> None:
        assert await execute(_registry(), "do_thing", AGENT_CTX, {"text": "x"}) == {"ok": "x"}

    async def test_agent_without_scope_forbidden(self) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(_registry(), "do_thing", STRANGER_CTX, {"text": "x"})
        assert exc.value.body.code == "CAPABILITY.FORBIDDEN"
        assert exc.value.http_status == 403

    async def test_no_actor_auth_required(self) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(_registry(), "do_thing", None, {"text": "x"})
        assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"
        assert exc.value.http_status == 401


class TestQuota:
    async def test_quota_exceeded(self) -> None:
        quota = CostQuota(default_daily_budget=9)  # cost=5,第二次 5+5>9
        reg = _registry()
        await execute(reg, "do_thing", USER_CTX, {"text": "a"}, quota=[quota])
        with pytest.raises(ServiceError) as exc:
            await execute(reg, "do_thing", USER_CTX, {"text": "b"}, quota=[quota])
        assert exc.value.body.code == "CAPABILITY.RATE_LIMITED"
        assert exc.value.http_status == 429
        assert quota.usage("local") == (5, 9)


class TestAudit:
    async def test_success_and_failure_recorded(self) -> None:
        sink = InMemoryAuditSink()
        reg = _registry()
        await execute(reg, "do_thing", USER_CTX, {"text": "a"}, audit=[sink])
        with pytest.raises(ServiceError):
            await execute(reg, "do_thing", STRANGER_CTX, {"text": "b"}, audit=[sink])
        assert [e.ok for e in sink.entries] == [True, False]
        assert sink.entries[1].error_code == "CAPABILITY.FORBIDDEN"
        assert sink.entries[0].trace_id  # trace_id 贯穿(§7.8)

    def test_args_summary_redacts_secrets(self) -> None:
        summary = summarize_args({"text": "hello", "api_key": "sk-xxx"})
        assert "sk-xxx" not in summary
        assert "***" in summary
        assert "hello" in summary

    def test_args_summary_redacts_credential_variants(self) -> None:
        """credential / api-key 等变体同样脱敏(子串匹配)。"""
        summary = summarize_args({"user_credential": "c1", "api-key": "k2"})
        assert "c1" not in summary and "k2" not in summary


class TestLongRunning:
    async def test_job_ref_passes(self) -> None:
        ref = await execute(_registry(long_running=True), "do_thing", USER_CTX, {"text": "x"})
        assert isinstance(ref, JobRef)

    async def test_sync_result_rejected_for_long_running(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="bad", description="坏的长任务", long_running=True)
        def bad() -> dict:
            return {"sync": True}  # 同步长任务视为缺陷(§7.3)

        with pytest.raises(ServiceError, match="JobRef"):
            await execute(reg, "bad", USER_CTX, {})

    async def test_sync_handler_supported(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="ping", description="ping")
        def ping() -> dict:
            return {"pong": True}

        assert await execute(reg, "ping", USER_CTX, {}) == {"pong": True}


class TestActorInjection:
    """parity 需要:handler 声明 _actor 时注入调用者 ActorRef;不声明则不可见。"""

    async def test_actor_injected_when_declared(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="whoami", description="回显调用者")
        def whoami(_actor: ActorRef = None) -> dict:
            return {"id": _actor.id if _actor else None}

        out = await execute(reg, "whoami", AGENT_CTX, {})
        assert out == {"id": "agent.main"}

    async def test_actor_not_injected_when_not_declared(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="ping2", description="无 _actor 参数")
        def ping2() -> dict:
            return {"pong": True}

        assert await execute(reg, "ping2", AGENT_CTX, {}) == {"pong": True}
