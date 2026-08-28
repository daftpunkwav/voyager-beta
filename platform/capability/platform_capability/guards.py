"""入口守卫:鉴权、限流配额、审计——框架层强制,handler 里不写(§7.3 / §7.5 / §7.6)。"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from platform_actor import ActorContext
from platform_contracts import ActorKind, ErrorSuffix, JobRef, ServiceError

if TYPE_CHECKING:  # 运行时循环导入规避;仅静态检查需要具体类型
    from platform_capability.registry import Registry

_DOMAIN = "capability"

#: 审计摘要中必须脱敏的入参键(子串匹配,不区分大小写)
SENSITIVE_KEYS = ("api_key", "api-key", "apikey", "token", "secret",
                  "password", "authorization", "credential")


@dataclass(frozen=True)
class CallRequest:
    capability: Any  # Capability(避免环依赖,结构化 duck type)
    actor: ActorContext | None
    args: dict[str, Any]


@dataclass(frozen=True)
class AuditEntry:
    actor_id: str
    actor_kind: str
    capability: str
    args_summary: str
    ok: bool
    error_code: str
    trace_id: str
    ts: float = field(default_factory=time.time)


class AuditSink(Protocol):
    def record(self, entry: AuditEntry) -> None: ...


def summarize_args(args: dict[str, Any], limit: int = 200) -> str:
    """入参摘要:脱敏 + 截断,用于审计落库。"""
    redacted = {
        k: ("***" if any(s in k.lower() for s in SENSITIVE_KEYS) else v)
        for k, v in args.items()
    }
    text = repr(redacted)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class LocalAuth:
    """本机鉴权(§7.4):user 恒可信;agent / external 需持有 capability 要求的全部 scopes。"""

    def __call__(self, req: CallRequest) -> None:
        if req.actor is None:
            raise ServiceError(_DOMAIN, ErrorSuffix.AUTH_REQUIRED, "缺少 actor 凭证")
        if req.actor.actor.kind is ActorKind.USER:
            return
        missing = [s for s in req.capability.scopes if not req.actor.has_scope(s)]
        if missing:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                f"缺少权限: {', '.join(missing)}",
                hint="在设置页为该 actor 授予对应能力白名单",
            )


class CostQuota:
    """能力配额(§7.5):按 capability.cost 扣减,每 actor 每日预算,超额 → RATE_LIMITED。"""

    def __init__(
        self, default_daily_budget: int = 1000, budgets: dict[str, int] | None = None
    ) -> None:
        self._default = default_daily_budget
        self._budgets = dict(budgets or {})
        self._usage: dict[tuple[str, str], int] = {}  # (actor_id, 日期) -> 已用

    def __call__(self, req: CallRequest) -> None:
        actor_id = req.actor.actor.id if req.actor else "anonymous"
        budget = self._budgets.get(actor_id, self._default)
        day = time.strftime("%Y-%m-%d")
        used = self._usage.get((actor_id, day), 0)
        if used + req.capability.cost > budget:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.RATE_LIMITED,
                f"本日配额将超限: {used}+{req.capability.cost}/{budget}",
                hint="次日重置,或在设置页调整配额",
            )
        self._usage[(actor_id, day)] = used + req.capability.cost

    def usage(self, actor_id: str) -> tuple[int, int]:
        """返回 (当日已用, 预算)。"""
        day = time.strftime("%Y-%m-%d")
        return (
            self._usage.get((actor_id, day), 0),
            self._budgets.get(actor_id, self._default),
        )


class InMemoryAuditSink:
    """开发/测试用审计 sink;生产落 audit.db(§7.6,后续接入)。"""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


def _record(sinks: list[AuditSink | Callable[[AuditEntry], None]], entry: AuditEntry) -> None:
    for sink in sinks:
        if hasattr(sink, "record"):
            sink.record(entry)  # type: ignore[union-attr]
        else:
            sink(entry)  # type: ignore[operator]


async def execute(
    registry: Registry,
    name: str,
    actor: ActorContext | None,
    args: dict[str, Any] | None = None,
    *,
    auth: list[Callable[[CallRequest], None]] | None = None,
    quota: list[Callable[[CallRequest], None]] | None = None,
    audit: list[AuditSink | Callable[[AuditEntry], None]] | None = None,
) -> Any:
    """统一执行入口:查表 → 鉴权 → 配额 → 校验入参 → 调用 → 审计。

    顺序即语义:先过守卫再执行业务;无论成败都落审计(带 trace_id)。
    内部分为 _run_guards(纯守卫)/ _invoke(校验+调用)两段,可独立测试;
    本函数只负责编排与审计收口。
    """
    args = dict(args or {})
    cap = registry.get(name)
    req = CallRequest(capability=cap, actor=actor, args=args)
    sinks = list(audit or [])

    def entry(ok: bool, error_code: str) -> AuditEntry:
        return AuditEntry(
            actor_id=actor.actor.id if actor else "anonymous",
            actor_kind=actor.actor.kind.value if actor else "none",
            capability=name,
            args_summary=summarize_args(args),
            ok=ok,
            error_code=error_code,
            trace_id=actor.trace_id if actor else "",
        )

    try:
        _run_guards(req, auth=auth, quota=quota)
        result = await _invoke(registry, cap, actor, args, name=name)
    except ServiceError as exc:
        await asyncio.to_thread(_record, sinks, entry(False, exc.body.code))
        raise
    except Exception:  # 非预期异常也落审计(INTERNAL),再原样上抛
        await asyncio.to_thread(_record, sinks, entry(False, "CAPABILITY.INTERNAL"))
        raise
    await asyncio.to_thread(_record, sinks, entry(True, ""))
    return result


def _run_guards(
    req: CallRequest,
    *,
    auth: list[Callable[[CallRequest], None]] | None,
    quota: list[Callable[[CallRequest], None]] | None,
) -> None:
    """守卫段:鉴权(auth 缺省挂 LocalAuth)→ 配额;失败以 ServiceError 拒绝。"""
    auth_hooks = [LocalAuth()] if auth is None else auth
    for hook in auth_hooks:
        hook(req)
    for hook in quota or ():
        hook(req)


async def _invoke(
    registry: Registry,
    cap,
    actor: ActorContext | None,
    args: dict[str, Any],
    *,
    name: str,
) -> Any:
    """调用段:入参校验(coerce)→ _actor 注入 → handler → 长任务返回约定。"""
    from platform_capability.define import coerce_input

    input_obj = coerce_input(cap.input_model, args, domain=registry.domain)
    # 约定:handler 声明 _actor 参数时注入调用者 ActorRef(parity:写 secret 等
    # 操作需要知道"是谁在调",§8.8;handler 不声明则不可见)
    params = inspect.signature(cap.handler).parameters
    inject = {"_actor": actor.actor} if (actor is not None and "_actor" in params) else {}

    def _call() -> Any:
        if cap.input_model is not None:
            return cap.handler(input_obj, **inject)
        return cap.handler(**args, **inject)

    # 同步 handler(典型:sqlite 短查询)离环执行;async handler(含 await LLM)留在事件循环
    if inspect.iscoroutinefunction(cap.handler):
        result = _call()
        if inspect.isawaitable(result):
            result = await result
    else:
        result = await asyncio.to_thread(_call)
    if cap.long_running and not isinstance(result, JobRef):
        raise ServiceError(
            registry.domain,
            ErrorSuffix.INTERNAL,
            f"长任务能力 {name} 必须返回 JobRef(同步长任务视为缺陷,§7.3)",
        )
    return result
