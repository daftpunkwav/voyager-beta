"""权限引擎(§9.9):四维判定——网络 / 文件 / 应用内 / 资源。

判定返回 Decision(允许 + 分级),L2 由调用方路由到询问用户;
资源维(轮数/token/并发)的计数在执行点,引擎只给上限值。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from agent.policy.levels import Level

NET_OFF, NET_WHITELIST, NET_ALL = "off", "whitelist", "all"

# 档位严格度(§9.9「每级只能更严」):off < whitelist < all
_NET_STRICTNESS = {NET_OFF: 0, NET_WHITELIST: 1, NET_ALL: 2}


def narrow_network(global_mode: str, requested: str) -> str:
    """网络档位收窄(§9.9):自建 subagent 指定的档位与全局档位取更严的一档。"""
    if _NET_STRICTNESS.get(requested, _NET_STRICTNESS[NET_WHITELIST]) < _NET_STRICTNESS.get(
        global_mode, _NET_STRICTNESS[NET_WHITELIST]
    ):
        return requested
    return global_mode


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
        settings=None,  # 可选设置句柄(有 get(key) 即可):网络判定热读当前值(§9.9)
    ) -> None:
        self.network = network or NetworkPolicy()
        self.fs = fs or FsPolicy()
        self.app = app or AppPolicy()
        self.resource = resource or ResourcePolicy()
        self.shell_level = shell_level
        self._settings = settings

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

    def _network_policy(self) -> NetworkPolicy:
        """本次判定用的网络档位:有 settings 句柄则热读当前值(改设置不重启即生效),
        没有则用构造时的快照(单元测试路径)。"""
        if self._settings is None:
            return self.network
        return NetworkPolicy(
            mode=self._settings.get("agent.network.mode"),
            domains=tuple(self._settings.get("agent.network.domains") or ()),
        )

    def _app_policy(self) -> AppPolicy:
        """本次判定用的应用内白名单:有 settings 句柄则热读当前值,否则用构造快照。
        非法值(非字符串列表)整份回落快照,不把坏设置当成全拒把 Agent 打残。
        """
        if self._settings is None:
            return self.app
        try:
            allowed_raw = self._settings.get("agent.app.allowed")
            denied_raw = self._settings.get("agent.app.denied")
            allowed = list(allowed_raw) if isinstance(allowed_raw, (list, tuple, set)) else None
            denied = list(denied_raw) if isinstance(denied_raw, (list, tuple, set)) else None
            if allowed is None or denied is None or not all(isinstance(x, str) for x in allowed + denied):
                return self.app
            return AppPolicy(allowed=frozenset(allowed), denied=frozenset(denied))
        except Exception:  # noqa: BLE001  # settings 异常时保守回落快照
            return self.app

    def _decide_network(self, action: Action) -> Decision:
        net = self._network_policy()
        if net.mode == NET_OFF:
            return Decision(False, reason="网络权限:关闭(设置里可改为白名单/全开)")
        # urlparse.hostname:去端口/去 userinfo(https://evil.com@github.com/ 实连 evil.com)
        # 并统一小写;裸域名(无 scheme)按原样处理
        host = (urlparse(action.target).hostname or "") if "://" in action.target \
            else action.target
        host = host.lower()
        if net.mode == NET_ALL:
            return Decision(True, Level.L1_NOTIFY, "网络全开")
        if any(host == d or host.endswith("." + d) for d in net.domains):
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

    @staticmethod
    def _matches_policy(name: str, entries: frozenset[str]) -> bool:
        """命中规则:精确相等、`*` 通配、或以 `*` 结尾的前缀(如 `notes__*`)。"""
        if "*" in entries:
            return True
        if name in entries:
            return True
        prefixes = [e[:-1] for e in entries if e.endswith("*") and len(e) > 1]
        return any(name.startswith(p) for p in prefixes)

    def _decide_app(self, action: Action) -> Decision:
        name = action.target
        app = self._app_policy()
        if self._matches_policy(name, app.denied):
            return Decision(False, reason=f"能力被显式禁用: {name}")
        if not self._matches_policy(name, app.allowed):
            return Decision(False, reason=f"能力不在白名单: {name}")
        if action.irreversible:
            return Decision(True, Level.L2_CONFIRM, "不可逆能力需确认")
        return Decision(True, Level.L1_NOTIFY if action.write else Level.L0_SILENT)

    def _decide_shell(self, action: Action) -> Decision:
        return Decision(True, self.shell_level, "命令执行默认需确认")
