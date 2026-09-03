"""用户 workspace/hooks 钩子能力(phase-78,§9.13)。

reload_user_hooks 是变更边界,与插件批准同权:仅 USER,agent actor 拒绝;
目录钉死 build_agent 装配时的 workspace/hooks,能力不接路径参数(防把
任意路径的 json 当 hook 装载)。list_user_hooks 只读,任何已鉴权 actor 可看。
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def _require_user(actor: ActorRef) -> None:
    if actor is None or actor.kind is not ActorKind.USER:
        raise ServiceError(
            "agent", ErrorSuffix.FORBIDDEN, "用户钩子重载仅限用户操作"
        )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="reload_user_hooks",
                description="重新加载 workspace/hooks/ 下的声明式用户钩子:无需重启,"
                            "按 user: 前缀卸旧再重装,领域事件订阅经既有 sync 收敛"
                            "(已批准插件的订阅不受影响)。返回 loaded 装载数、"
                            "event_patterns 当前全量订阅、skipped 无法解析的文件",
                cost=1)
    async def reload_user_hooks(_actor: ActorRef = None) -> dict:
        _require_user(_actor)
        return deps.user_hooks.reload()

    @capability(reg, name="list_user_hooks",
                description="只读列出 workspace/hooks/ 下的 hook json:"
                            "文件名 / on / enabled / description / 是否已装载")
    def list_user_hooks() -> dict:
        return {"items": deps.user_hooks.list()}
