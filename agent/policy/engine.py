"""权限引擎(§9.9):四维判定——网络 / 文件 / 应用内 / 资源。

判定返回 Decision(允许 + 分级),L2 由调用方路由到询问用户;
资源维(轮数/token/并发)的计数在执行点,引擎只给上限值。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.policy.levels import Level

NET_OFF, NET_WHITELIST, NET_ALL = "off", "whitelist", "all"


@dataclass(frozen=True)
class NetworkPolicy:
    mode: str = NET_WHITELIST
    domains: tuple[str, ...] = ("github.com", "arxiv.org")


@dataclass(frozen=True)
class FsPolicy:
    roots: tuple[str, ...] = ("workspace",)  # fs jail 根(§9.10)


@dataclass(frozen=True)
class AppPolicy:
    """应用内权限:能力白名单(细到单个能力);secret 设置项永远拒绝(§8.8,框架层强制)。"""

    allowed: frozenset[str] = frozenset({"*"})
    denied: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ResourcePolicy:
    max_rounds: int = 20  # ReAct 轮数上限(§9.19)
    max_tool_calls: int = 40
    max_subagents: int = 3
    daily_tokens: int = 0  # 0 = 不限


@dataclass(frozen=True)
class Action:
    dimension: str  # network | fs | app | shell | resource | none
    target: str = ""  # url / path / 能力名 / 命令
    write: bool = False
    irreversible: bool = False
    detail: str = ""


@dataclass(frozen=True)
class Decision:
    allow: bool
    level: Level = Level.L0_SILENT
    reason: str = ""


class PolicyEngine:
    """四维权限判定。判定是纯函数;确认交互在 tools/base.py 的 Toolbelt。"""

    def __init__(
        self,
        *,
        network: NetworkPolicy | None = None,
        fs: FsPolicy | None = None,
        app: AppPolicy | None = None,
        resource: ResourcePolicy | None = None,
        shell_level: Level = Level.L2_CONFIRM,
    ) -> None:
        self.network = network or NetworkPolicy()
        self.fs = fs or FsPolicy()
        self.app = app or AppPolicy()
        self.resource = resource or ResourcePolicy()
        self.shell_level = shell_level

    def decide(self, action: Action) -> Decision:
        handler = {
            "network": self._decide_network,
            "fs": self._decide_fs,
            "app": self._decide_app,
            "shell": self._decide_shell,
        }.get(action.dimension)
        if handler is None:
            return Decision(allow=True)  # none/resource 等:L0
        return handler(action)

    def _decide_network(self, action: Action) -> Decision:
        if self.network.mode == NET_OFF:
            return Decision(False, reason="网络权限:关闭(设置里可改为白名单/全开)")
        host = action.target.split("/")[2] if "://" in action.target else action.target
        if self.network.mode == NET_ALL:
            return Decision(True, Level.L1_NOTIFY, "网络全开")
        if any(host == d or host.endswith("." + d) for d in self.network.domains):
            return Decision(True, Level.L1_NOTIFY, f"白名单域名: {host}")
        return Decision(False, reason=f"域名不在白名单: {host}(可在设置页添加)")

    def _decide_fs(self, action: Action) -> Decision:
        target = Path(action.target)
        if not target.is_absolute() and self.fs.roots:
            target = Path(self.fs.roots[0]) / target  # 相对路径以 jail 根为基准(与 fs 工具一致)
        target = target.resolve()
        for root in self.fs.roots:
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                if action.irreversible:
                    return Decision(True, Level.L2_CONFIRM, "删除类操作需确认")
                return Decision(
                    True, Level.L1_NOTIFY if action.write else Level.L0_SILENT
                )
        return Decision(
            False, reason=f"路径在工作目录之外: {target}(fs jail,§9.9/§9.10)"
        )

    def _decide_app(self, action: Action) -> Decision:
        name = action.target
        if name in self.app.denied:
            return Decision(False, reason=f"能力被显式禁用: {name}")
        if "*" not in self.app.allowed and name not in self.app.allowed:
            return Decision(False, reason=f"能力不在白名单: {name}")
        if action.irreversible:
            return Decision(True, Level.L2_CONFIRM, "不可逆能力需确认")
        return Decision(True, Level.L1_NOTIFY if action.write else Level.L0_SILENT)

    def _decide_shell(self, action: Action) -> Decision:
        return Decision(True, self.shell_level, "命令执行默认需确认")
