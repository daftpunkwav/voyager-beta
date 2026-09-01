"""权限引擎(§9.9):四维判定——网络 / 文件 / 应用内 / 资源。

判定返回 Decision(允许 + 分级),L2 由调用方路由到询问用户;
资源维(轮数/token/并发)的计数在执行点,引擎只给上限值。
"""

from __future__ import annotations

import ipaddress
import re
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


def _host_is_nonglobal(host: str) -> bool:
    """环回/内网/链路本地/本机名的字面判断;只看 URL 里已写出的 host,不做 DNS。
    字面规则对齐 services/llm 的同名判定(不跨包 import),但网络维没有 USER 例外:
    web_fetch 打 127.0.0.1 是 SSRF,一律拒绝。空 host(解析失败)不算非全局。"""
    h = (host or "").lower().rstrip(".")
    if h in {"localhost", "metadata.google.internal"} or h.endswith(".localhost"):
        return True
    try:
        addr = ipaddress.ip_address(h)
        mapped = getattr(addr, "ipv4_mapped", None)
        return not (mapped or addr).is_global
    except ValueError:
        return False


# 复制/移动/删除类动词表:skills 刀(41)与只读附加根刀(58)共用,防两处漂移
_SHELL_WRITE_VERBS = r"cp|mv|move|copy|xcopy|rm|del|erase|rd|rmdir|unlink|touch|tee"

# shell 维 skills 禁写(phase-41,补 32 的 shell 旁路):保守正则识别「明显要写/删
# skills 子树」的字面量,不做完整 shell 解析——宁可漏拦 py -c 内联写文件等复杂变形,
# 也不误杀 grep skills/README、type skills\keep\SKILL.md 这类只读命令。
# 路径段允许 ./ ../ 与普通段前缀(repo/../skills/ 解析后仍落 skills);必须带分隔符,
# 避免误杀 skills.txt、skills_backup 这类同名前缀。
_SKILLS_PATH = r"(?:(?:\.{1,2}|[\w.-]+)[/\\])*skills[/\\]"
# 分支一:重定向(> / >> / 2>)进 skills;分支二:复制/移动/删除类动词 + skills 路径
_SHELL_SKILLS_WRITE_RE = re.compile(
    r">>?\s*['\"]?" + _SKILLS_PATH
    + r"|\b(?:" + _SHELL_WRITE_VERBS + r")\b"
    + r"[^|;&>\n]*" + _SKILLS_PATH,
    re.IGNORECASE,
)


def _shell_targets_skills_write(cmd: str) -> bool:
    """命令字符串是否明显要把内容写入/删除 skills 子树(保守识别,phase-41)。"""
    return bool(_SHELL_SKILLS_WRITE_RE.search(cmd or ""))


# shell 维只读附加根守卫(phase-58,补 53 的 shell 旁路):与 41 同精神保守识别,
# 不做完整 shell 解析——复杂变形(py -c 内联写文件、变量拼接路径)可漏拦。
# write_roots 内路径按可写对待不拦(与 fs 维 55 一致,仍走 L2);相对路径以 workspace
# 为 cwd(35),天然落在 jail 内,不经本函数处理(skills 仍走 41)。
# 写/删意图粗筛:分支一为重定向(> / >> / 2>)指向绝对路径,分支二为出现动词表动词。
_SHELL_WRITE_INTENT_RE = re.compile(
    r">>?\s*['\"]?(?:[A-Za-z]:[/\\]|/)|\b(?:" + _SHELL_WRITE_VERBS + r")\b",
    re.IGNORECASE,
)
# 命令里的绝对路径字面量(Windows 盘符 / Unix 根);引号、空白、管道、分号、重定向符截断
_SHELL_ABS_PATH_RE = re.compile(r"[A-Za-z]:[/\\][^\s|;&\"']*|/[^\s|;&\"']*")


def _shell_targets_read_root_write(
    cmd: str, read_roots: tuple[str, ...], write_roots: tuple[str, ...]
) -> bool:
    """命令字符串是否明显要把内容写入/删除只读附加根子树(保守识别,phase-58)。

    先用意图粗筛(重定向或复制/移动/删除类动词),命中再提取命令里的绝对路径
    字面量逐个 resolve:落在某只读附加根下、且不在任何读写根下 → True(应拒,
    先于 L2)。路径同时落在读写根下按可写对待(对齐 _decide_fs 的 roots 顺序)。"""
    if not _SHELL_WRITE_INTENT_RE.search(cmd or ""):
        return False
    for raw in _SHELL_ABS_PATH_RE.findall(cmd or ""):
        target = Path(raw).resolve()
        writable = False
        for root in write_roots:  # 读写根优先于只读根(与 fs 维同序)
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                writable = True
                break
        if writable:
            continue
        for root in read_roots:
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                return True
    return False


@dataclass(frozen=True)
class NetworkPolicy:
    mode: str = NET_WHITELIST
    domains: tuple[str, ...] = ("github.com", "arxiv.org")


@dataclass(frozen=True)
class FsPolicy:
    roots: tuple[str, ...] = ("workspace",)  # fs jail 根(§9.10)
    read_roots: tuple[str, ...] = ()  # 附加只读根(§9.9):读放行,写/删一律拒绝
    write_roots: tuple[str, ...] = ()  # 附加读写根(§9.9/§9.10):读 L0,写/删 L2;workspace 优先


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
        # 顺序冻结(§9.9 网络维):off → 非全局 → all/白名单。
        # 非全局字面量先于档位分支:ALL 档也不打环回/内网(SSRF),白名单写了也不放行
        if _host_is_nonglobal(host):
            return Decision(False, reason="网络权限:拒绝环回或内网地址")
        if net.mode == NET_ALL:
            return Decision(True, Level.L1_NOTIFY, "网络全开")
        if any(host == d or host.endswith("." + d) for d in net.domains):
            return Decision(True, Level.L1_NOTIFY, f"白名单域名: {host}")
        return Decision(False, reason=f"域名不在白名单: {host}(可在设置页添加)")

    def _fs_policy(self) -> FsPolicy:
        """本次判定用的 fs 策略:有 settings 句柄则热读附加只读根与读写根(§9.9,改设置
        不重启即生效),没有则用构造时的快照(单元测试路径)。roots(workspace)
        不热读——workspace 变更是装配期的事。坏值(非字符串列表)整份回落快照。"""
        if self._settings is None:
            return self.fs
        try:
            read_raw = self._settings.get("agent.fs.read_roots")
            write_raw = self._settings.get("agent.fs.write_roots")
            if read_raw is None and write_raw is None:
                return self.fs
            if read_raw is not None and (
                not isinstance(read_raw, (list, tuple, set))
                or not all(isinstance(x, str) for x in read_raw)
            ):
                return self.fs
            if write_raw is not None and (
                not isinstance(write_raw, (list, tuple, set))
                or not all(isinstance(x, str) for x in write_raw)
            ):
                return self.fs
            return FsPolicy(
                roots=self.fs.roots,
                read_roots=tuple(read_raw) if read_raw is not None else self.fs.read_roots,
                write_roots=tuple(write_raw) if write_raw is not None else self.fs.write_roots,
            )
        except Exception:  # noqa: BLE001  # settings 异常时保守回落快照
            return self.fs

    def _decide_fs(self, action: Action) -> Decision:
        fs = self._fs_policy()
        target = Path(action.target)
        if not target.is_absolute() and fs.roots:
            target = Path(fs.roots[0]) / target  # 相对路径以 jail 根为基准(与 fs 工具一致)
        target = target.resolve()
        for root in fs.roots:
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                if action.write or action.irreversible:
                    # skills 目录禁写禁删(phase-32):SKILL.md 一旦可写,提示注入
                    # 下一轮即进 system 的「可用 skill」索引;拒绝必须发生在本判定,
                    # 先于 L2 确认(delete 不该先弹「允许删除吗?」再失败)
                    reserved = root_path / "skills"
                    if target == reserved or reserved in target.parents:
                        return Decision(False, reason="skill 目录禁止经文件工具改写")
                if action.irreversible:
                    return Decision(True, Level.L2_CONFIRM, "删除类操作需确认")
                return Decision(
                    True, Level.L1_NOTIFY if action.write else Level.L0_SILENT
                )
        # 附加读写根(phase-55,§9.9/§9.10):用户显式配置的可写白名单目录,读 L0、
        # 写/删 L2 确认(§9.10「用户目录默认只读,写入须 L2」)。判在 read_roots 之前:
        # 路径同时落在读写根与只读根下时按可写对待。skills 禁写特例不在这里另判——
        # 它只属于 workspace jail,落在 roots 循环里,write_roots 旁路不了。
        for root in fs.write_roots:
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                if action.irreversible:
                    return Decision(True, Level.L2_CONFIRM, "用户目录删除需确认(§9.10)")
                if action.write:
                    return Decision(True, Level.L2_CONFIRM, "用户目录写入需确认(§9.10)")
                return Decision(True, Level.L0_SILENT)
        # workspace jail 与读写根之外:附加只读根(§9.9)只放行读;写/删一律拒绝(先于 L2,
        # 附加根不做删除确认——确认了也没有写权限)。skills 特例无需另判:附加根本
        # 身已拒写。roots 优先于 read_roots:workspace 及其子树不受附加根只读约束。
        for root in fs.read_roots:
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                if action.write or action.irreversible:
                    return Decision(
                        False,
                        reason=f"附加根目录只读,写/删仅限工作目录: {target}(§9.9)",
                    )
                return Decision(True, Level.L0_SILENT)
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
        # skills 子树禁经 shell 改写(phase-41):拒绝发生在 L2 确认之前(与 32 的 fs 刀一致)
        if (action.write or action.irreversible) and _shell_targets_skills_write(action.target):
            return Decision(False, reason="skill 目录禁止经 shell 改写")
        # 只读附加根禁经 shell 改写(phase-58,补 53 的 shell 旁路):同样先于 L2 拒绝;
        # write_roots 内路径不拦(与 fs 维一致,仍走 L2)。附加根热读,与 fs 判定同源。
        if action.write or action.irreversible:
            fs = self._fs_policy()
            if _shell_targets_read_root_write(action.target, fs.read_roots, fs.write_roots):
                return Decision(False, reason="只读附加目录禁止经 shell 改写")
        return Decision(True, self.shell_level, "命令执行默认需确认")
