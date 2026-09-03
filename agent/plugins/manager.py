"""插件发现与批准(§9.13,phase-72 整包 / phase-74 分项)。

插件 = 插件根目录下一个子目录,含声明式清单 plugin.json(样例 plugins/_example):
skills 指向 SKILL.md 目录、hooks 指向 hook json、mcp 指向外接 MCP 配置。
声明式 only:插件不 import 平台实现、不执行任意代码;装载顺序是
发现(list 可见)→ 用户批准(整包或分项)→ skill 进 SkillLoader roots / hook 进
HookRegistry / MCP 只登记待批准条目(不自动 approve_mcp_tools)。

选型(写回钉死):
- `_` 前缀目录(如 `_example`)**照常被 list 看到**,与其他插件同规则——
  未批准一律不装载;`_` 前缀只是「示例/未完成」的命名约定,不是加载器跳过逻辑。
- 批准名单持久化:旧键 `agent.plugins.approved`(list[str],整包)与新键
  `agent.plugins.approvals`(dict,分项)并存,均 user_only。写侧互斥:
  整包批准写 approved 并从 approvals 删名;分项批准写 approvals 并从
  approved 删名;撤销两键都清。读侧因此天然无优先级歧义,且只有旧键的
  存量数据按整包 "*" 装载(向后兼容,phase-74 A2)。
- 分项勾选粒度:skill 按 skill 名(SKILL.md 父目录名)、hook 按**文件相对路径**
  (同 on 可多文件,目录粒度不够)、MCP 按 mcp.json 的 server id。
- 勾了但清单当前没有的名字(插件改版/删文件)→ 跳过并在返回 `skipped`
  披露,持久化仍保留原勾选(不改写用户意图;恢复文件后重装即生效)。
  空提交(三类全空)拒绝 INVALID_INPUT;非法参数值拒绝;禁止静默装错名。
- 装载幂等:每次批准/分项修改都先整插件热卸再按当前勾选装载
  (72 自审:先 unload 再 apply,重复批准不重复注册)。
- 运行期订阅同步(phase-75):装载/热卸 hook 会改 HookRegistry.event_patterns,
  build_agent 在 EventLoop 构造后注入 `set_subscription_sync`,本管理器在
  热卸/装载完成后把当前 event_patterns 全量推给 loop(批准即订 / 撤销即退,
  免重启;loop 侧幂等 diff,启动装载阶段 sync 未注入是 no-op)。
- MCP 回收(phase-76,选型 S3):撤销插件 / 分项去勾时回收本插件登记过的
  外接 MCP——仅限「未批准任何工具」的条目;工具已批准(用户显式依赖)、
  其他已批准插件仍声明勾选、配置与插件声明对不上(疑为手工同 id)的一律
  跳过并在返回体 mcp_reclaim_skipped 披露。回收路径与 remove_mcp_server
  等价(unmount + drop_session + delete_config),禁止只删配置留挂载幽灵。
- contains 路径 jail:声明相对路径 resolve 后必须仍在插件目录内(拒 `../` 逃逸)。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from agent.clients.pool import validate_server_config
from agent.hooks.loader import HookLoader
from agent.hooks.triggers import HookRegistry
from agent.skills.loader import SkillLoader

log = logging.getLogger("agent.plugins")

#: 批准名单的设置键(user_only;与 MCP/敏感设置同权,phase-13 同精神)
APPROVED_KEY = "agent.plugins.approved"
#: 分项批准状态的设置键(user_only;phase-74)
APPROVALS_KEY = "agent.plugins.approvals"


@dataclass(frozen=True)
class Approval:
    """一次生效的批准选择:三类各自的 (是否全部, 名单)。"""

    skills_all: bool = False
    skills: frozenset[str] = frozenset()  # skill 名
    hooks_all: bool = False
    hooks: frozenset[str] = frozenset()  # hook 文件相对路径
    mcp_all: bool = False
    mcp: frozenset[str] = frozenset()  # mcp.json 的 server id

    @property
    def empty(self) -> bool:
        """三类都没勾(空提交;item 批准拒绝,防「记了名却什么都没装」)。"""
        return not (
            self.skills_all or self.skills or self.hooks_all or self.hooks
            or self.mcp_all or self.mcp
        )


#: 整包 = 三类全选(72 语义;MCP 仍只登记,不自动批准工具)
BUNDLE = Approval(skills_all=True, hooks_all=True, mcp_all=True)


@dataclass(frozen=True)
class PluginManifest:
    """plugin.json 解析产物;permissions / contains 保留原始形状。"""

    name: str
    version: str
    description: str
    permissions: dict
    contains: dict
    path: Path  # 插件目录(绝对)


def load_manifest(plugin_dir: Path) -> PluginManifest | None:
    """解析单个 plugin.json;坏 JSON / 非 dict / 缺 name → None(调用方跳过,不炸 boot)。"""
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    permissions = data.get("permissions")
    contains = data.get("contains")
    return PluginManifest(
        name=name,
        version=str(data.get("version") or ""),
        description=str(data.get("description") or ""),
        permissions=permissions if isinstance(permissions, dict) else {},
        contains=contains if isinstance(contains, dict) else {},
        path=plugin_dir,
    )


def discover(root: str | Path) -> list[PluginManifest]:
    """扫描根下每个含 plugin.json 的子目录(按目录名排序;含 `_` 前缀,坏的不进)。"""
    base = Path(root)
    if not base.is_dir():
        return []
    out: list[PluginManifest] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        manifest = load_manifest(child)
        if manifest is not None:
            out.append(manifest)
    return out


def resolve_within(base: Path, rel: object) -> Path | None:
    """contains 相对路径 → 绝对路径;空串 / 逃出 base(`../`、绝对路径)→ None(C4 jail)。"""
    text = str(rel or "").strip()
    if not text:
        return None
    candidate = (base / text).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate


def _items(raw: object) -> list[object]:
    """contains 条目归一:字符串或列表都按列表处理。"""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        return [raw]
    return []


def parse_choice(raw: object, field: str) -> tuple[bool, set[str]]:
    """分项入参归一:(True, 空)= "*" 全选;(False, names)= 名称列表。

    None → (False, 空) = 该项不涉及(不装载、不 skipped);列表元素须为非空
    str,否则 INVALID_INPUT(禁止把脏类型当空勾选静默放过)。
    """
    if raw is None:
        return False, set()
    if raw == "*":
        return True, set()
    if isinstance(raw, list):
        bad = [x for x in raw if not isinstance(x, str) or not x.strip()]
        if bad:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT,
                f"{field} 须为 '*' 或非空名称列表,收到: {bad!r}",
            )
        return False, {str(x) for x in raw}
    raise ServiceError(
        "agent", ErrorSuffix.INVALID_INPUT,
        f"{field} 须为 '*' 或名称列表: {raw!r}",
    )


def parse_approval(raw: object) -> Approval | None:
    """持久化 approvals[name] → Approval;坏形状(非 dict / 非法值)→ None(视为未批准)。"""
    if not isinstance(raw, dict):
        return None
    try:
        skills_all, skills = parse_choice(raw.get("skills"), "skills")
        hooks_all, hooks = parse_choice(raw.get("hooks"), "hooks")
        mcp_all, mcp = parse_choice(raw.get("mcp"), "mcp")
    except ServiceError:
        return None
    return Approval(
        skills_all=skills_all, skills=frozenset(skills),
        hooks_all=hooks_all, hooks=frozenset(hooks),
        mcp_all=mcp_all, mcp=frozenset(mcp),
    )


def manifest_skills(manifest: PluginManifest) -> list[Path]:
    """contains.skills 中真实存在 SKILL.md 的目录(jail 之外的条目丢弃)。"""
    out: list[Path] = []
    for rel in _items(manifest.contains.get("skills")):
        path = resolve_within(manifest.path, rel)
        if path is not None and (path / "SKILL.md").is_file():
            out.append(path)
    return out


def manifest_skill_entries(manifest: PluginManifest) -> list[tuple[Path, str]]:
    """(skill 目录, skill 名) 列表;与 SkillLoader._scan 同规则(SKILL.md 父目录名)。

    分项勾选按 skill 名;同名多目录时逐一列出、装载时全部 add_root(由插件
    作者保证不重名;contains 一条 rel 通常就是一个单 skill 根)。
    """
    out: list[tuple[Path, str]] = []
    for skill_dir in manifest_skills(manifest):
        for name in skill_names_in(skill_dir):
            out.append((skill_dir, name))
    return out


def manifest_hook_entries(manifest: PluginManifest) -> list[tuple[Path, str]]:
    """(hook json 绝对路径, 声明相对路径) 列表;rel 即分项勾选 id(同 on 可多文件)。"""
    out: list[tuple[Path, str]] = []
    for rel in _items(manifest.contains.get("hooks")):
        text = str(rel or "").strip()
        if not text:
            continue
        path = resolve_within(manifest.path, text)
        if path is not None and path.is_file():
            out.append((path, text))
    return out


def manifest_mcp(manifest: PluginManifest) -> Path | None:
    """contains.mcp 指向且真实存在的 mcp.json 路径;未声明 / 缺文件 → None。"""
    path = resolve_within(manifest.path, manifest.contains.get("mcp"))
    if path is not None and path.is_file():
        return path
    return None


def manifest_mcp_servers(manifest: PluginManifest) -> dict[str, dict]:
    """mcp.json 解析出的 servers dict;缺 / 坏 / 空 → {}。"""
    path = manifest_mcp(manifest)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    servers = data.get("servers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else {}


def _plugin_server_config(sid: str, raw: object) -> dict:
    """mcp.json 的单条 server 声明 → 归一配置(登记与回收守卫共用同一变换)。

    非法声明(缺 command / 坏 url 等)抛 AGENT.INVALID_INPUT,调用方按跳过处理。
    """
    entry = dict(raw) if isinstance(raw, dict) else {}
    entry["id"] = str(sid)
    entry.setdefault("kind", "url" if entry.get("url") else "stdio")
    return validate_server_config({**entry, "approval": "item"})


def skill_names_in(skill_dir: Path) -> list[str]:
    """目录下的 skill 名(与 SkillLoader._scan 同规则:SKILL.md 的父目录名)。"""
    return [p.parent.name for p in sorted(skill_dir.rglob("SKILL.md"))]


class PluginManager:
    """发现 + 批准名单 + 装载/热卸;capability 层经它实现 list/批准两能力。"""

    def __init__(
        self,
        root: str | Path,
        *,
        settings: Any,  # SettingsStore(读/写 agent.plugins.approved / approvals)
        skills: SkillLoader,
        hooks: HookRegistry,
        mcp: Any | None = None,  # McpClientPool(批准时登记 MCP 条目;可省)
        set_subscription_sync: Callable[[tuple[str, ...]], None] | None = None,
        # phase-75:EventLoop 注入的订阅同步入口(装载/热卸后推 hooks.event_patterns)
    ) -> None:
        self._root = Path(root)
        self._settings = settings
        self._skills = skills
        self._hooks = hooks
        self._mcp = mcp
        self._set_subscription_sync = set_subscription_sync

    def set_subscription_sync(
        self, sync: Callable[[tuple[str, ...]], None] | None
    ) -> None:
        """注入/替换订阅同步回调(build_agent 在 EventLoop 构造后调用)。

        sync 每次收到当前 hooks.event_patterns 全量;注入后先同步一次基线,
        避免注入前已装载插件(启动装载)的 pattern 缺同步。
        """
        self._set_subscription_sync = sync
        if sync is not None:
            self._sync_subscription()

    def _sync_subscription(self) -> None:
        """把当前声明式 hook 领域事件订阅推给 EventLoop(未注入时 no-op)。

        装载(apply/_apply_selected)或热卸(unload/_unload_manifest)都会改
        event_patterns,结束后全量同步一次;loop 侧幂等 diff,只动差异。
        """
        if self._set_subscription_sync is not None:
            self._set_subscription_sync(self._hooks.event_patterns)

    # ---- 发现与清单形状(list_plugins 数据源) ----

    def manifests(self) -> list[PluginManifest]:
        return discover(self._root)

    def find(self, name: str) -> PluginManifest | None:
        return next((m for m in self.manifests() if m.name == name), None)

    def approved_names(self) -> list[str]:
        """整包批准名单(旧键,72 语义)。"""
        value = self._settings.get(APPROVED_KEY)
        if not isinstance(value, list):
            return []
        return [str(n) for n in value]

    def loadable_names(self) -> list[str]:
        """两键(整包 + 分项)并集:build_agent 启动装载的候选名单。"""
        names = list(self.approved_names())
        approvals = self.approvals()
        for n in approvals:
            if n not in names:
                names.append(n)
        return names

    def approvals(self) -> dict[str, dict]:
        """分项批准原始存储(新键);坏形状整体按空处理,不炸 boot。"""
        value = self._settings.get(APPROVALS_KEY)
        if not isinstance(value, dict):
            return {}
        return {str(k): v for k, v in value.items() if isinstance(v, dict)}

    def _approval_of(self, manifest: PluginManifest) -> Approval | None:
        """该插件当前生效的批准;未批准 → None。

        分项键优先(存在即按其装载);否则退回整包名单(存量旧数据按 "*")。
        坏分项数据 / 空分项(全空列表,写侧本会拒绝)→ None,与写侧语义一致
        (空 = 没批准任何东西,不装载也不炸)。
        """
        raw = self.approvals().get(manifest.name)
        if raw is not None:
            approval = parse_approval(raw)
            if approval is not None and approval.empty:
                return None
            return approval
        if manifest.name in set(self.approved_names()):
            return BUNDLE
        return None

    def list(self) -> list[dict]:
        """list_plugins items:稳定形状 phase-72 契约 + phase-74 明细。

        每项在 contains 计数之外平铺 skills/hooks/mcp 明细(名字 / on /
        文件路径 / enabled / 当前勾选 approved);MCP 工具批准状态只读既有
        MCP 存储(registered / tools_approved),分项勾选与登记状态分离。
        """
        approvals = self.approvals()
        items = []
        for m in self.manifests():
            approval = self._approval_of(m)
            skills_seen: dict[str, Path] = {}
            for skill_dir, sname in manifest_skill_entries(m):
                skills_seen.setdefault(sname, skill_dir)
            hook_entries = manifest_hook_entries(m)
            servers = manifest_mcp_servers(m)
            if approval is None:
                granularity = ""
            elif m.name in approvals:
                granularity = "item"
            else:  # 只可能在整包名单
                granularity = "bundle"
            selected_skills = (
                None if approval is None or approval.skills_all else approval.skills
            )
            selected_hooks = (
                None if approval is None or approval.hooks_all else approval.hooks
            )
            selected_mcp = None if approval is None or approval.mcp_all else approval.mcp
            items.append(
                {
                    "name": m.name,
                    "version": m.version,
                    "description": m.description,
                    "approved": approval is not None,
                    "granularity": granularity,
                    "permissions": {
                        "scopes": [str(s) for s in _items(m.permissions.get("scopes"))],
                        "network": str(m.permissions.get("network") or ""),
                        "fs": str(m.permissions.get("fs") or ""),
                    },
                    "contains": {
                        "skills": len(manifest_skills(m)),
                        "hooks": len(hook_entries),
                        "mcp": bool(servers),
                    },
                    "skills": [
                        {
                            "name": name,
                            "approved": approval is not None
                            and (selected_skills is None or name in selected_skills),
                        }
                        for name in skills_seen
                    ],
                    "hooks": [
                        {
                            "path": rel,
                            "on": _hook_on(path),
                            "enabled": _hook_enabled(path),
                            "approved": approval is not None
                            and (selected_hooks is None or rel in selected_hooks),
                        }
                        for path, rel in hook_entries
                    ],
                    "mcp": [
                        {
                            "id": sid,
                            "approved": approval is not None
                            and (selected_mcp is None or sid in selected_mcp),
                            "registered": self._mcp is not None
                            and self._mcp.find_config(sid) is not None,
                            "tools_approved": _mcp_tools_approved(self._mcp, sid),
                        }
                        for sid in servers
                    ],
                    "path": m.path.name,
                }
            )
        return items

    # ---- 装载 / 热卸(build_agent 启动与批准动作共用) ----

    def apply(self, name: str) -> dict:
        """按当前持久化批准装载该插件(build_agent 启动 / 重启用)。

        未批准(或插件目录不在)→ 空装载不炸;分项状态照常只装勾选子集。
        """
        manifest = self._require(name)
        approval = self._approval_of(manifest)
        if approval is None:
            return {"skills": [], "hooks": 0}
        return self._apply_selected(manifest, approval)

    def _apply_selected(self, manifest: PluginManifest, approval: Approval) -> dict:
        """装载插件的 skill 目录与 hook 文件(按勾选过滤);返回 loaded 计数。

        先热卸再装载(幂等):重复批准 / 批准重试 / 分项改勾都不会重复注册
        hook、重复加 skill root。
        """
        self._unload_manifest(manifest)
        skill_names: list[str] = []
        for skill_dir, sname in manifest_skill_entries(manifest):
            if approval.skills_all or sname in approval.skills:
                self._skills.add_root(skill_dir)
                skill_names.append(sname)
        hook_count = 0
        loader = HookLoader(self._hooks)
        for hook_path, rel in manifest_hook_entries(manifest):
            if not (approval.hooks_all or rel in approval.hooks):
                continue
            try:
                hook_count += loader.load_file(
                    hook_path, source=f"plugin:{manifest.name}", approved=True
                )
            except Exception:  # noqa: BLE001  # 单文件坏 json 不炸批准;记日志披露,计数不计
                log.warning("插件 %s 的 hook 文件装载失败: %s", manifest.name, rel)
        self._sync_subscription()  # phase-75:装载改了事件订阅,同步给 EventLoop
        return {"skills": skill_names, "hooks": hook_count}

    def unload(self, name: str) -> dict:
        """热卸:移除 skill roots 与该插件 source 的 hook 注册;返回移除计数。"""
        return self._unload_manifest(self._require(name))

    def _unload_manifest(self, manifest: PluginManifest) -> dict:
        """按 manifest 热卸;approve(幂等化)与 unload 共用。"""
        removed_skills = 0
        for skill_dir in manifest_skills(manifest):
            if self._skills.remove_root(skill_dir):
                removed_skills += 1
        removed_hooks = self._hooks.remove_source(f"plugin:{manifest.name}:")
        # 声明过的事件订阅一并撤(phase-28 精确订阅);但其他已批准插件
        # 仍声明同一 pattern 时保留订阅,不误伤它们的 hook 触发
        for on in self._declared_ons(manifest):
            if not self._pattern_still_wanted(manifest.name, on):
                self._hooks.forget_event_pattern(on)
        self._sync_subscription()  # phase-75:热卸改了事件订阅,同步给 EventLoop
        return {"skills": removed_skills, "hooks": removed_hooks}

    # ---- 批准 / 撤销(capability 层入口;actor 落审计) ----

    async def approve(self, name: str, actor: ActorRef) -> dict:
        """整包批准(72 契约):三类全装;MCP 全登记待批准;不自动批准工具。"""
        manifest = self._require(name)
        loaded = self._apply_selected(manifest, BUNDLE)
        registered, mcp_skipped = await self._register_mcp(manifest, actor, BUNDLE)
        names = self.approved_names()
        if manifest.name not in names:
            await self._settings.set(APPROVED_KEY, sorted([*names, manifest.name]), actor)
        # 曾分项批准过:整包覆盖,清掉分项状态,避免读侧歧义
        if manifest.name in self.approvals():
            await self._clear_approvals(manifest.name, actor)
        return self._approval_result(manifest.name, loaded, registered, mcp_skipped)

    async def approve_item(
        self,
        name: str,
        actor: ActorRef,
        *,
        skills: object = None,
        hooks: object = None,
        mcp: object = None,
    ) -> dict:
        """分项批准:只装载勾选的 skill / hook / MCP;空提交拒绝;未知名跳过披露。

        改勾去掉了原先勾选的 mcp id(phase-76 A4):与整包撤销同一套安全规则
        回收被去掉的 id,结果在返回体 mcp_reclaimed / mcp_reclaim_skipped 披露。
        """
        manifest = self._require(name)
        old = self._approval_of(manifest)  # 改勾前的生效批准(A4 去勾回收要对比)
        skills_all, skills_set = parse_choice(skills, "skills")
        hooks_all, hooks_set = parse_choice(hooks, "hooks")
        mcp_all, mcp_set = parse_choice(mcp, "mcp")
        approval = Approval(
            skills_all=skills_all, skills=frozenset(skills_set),
            hooks_all=hooks_all, hooks=frozenset(hooks_set),
            mcp_all=mcp_all, mcp=frozenset(mcp_set),
        )
        if approval.empty:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT,
                "自定义批准至少要勾选一项(skill / hook / MCP)",
            )
        loaded = self._apply_selected(manifest, approval)
        skipped = self._skipped_for(manifest, approval)
        registered, mcp_reg_skipped = await self._register_mcp(manifest, actor, approval)
        payload = {
            "skills": "*" if skills_all else sorted(skills_set),
            "hooks": "*" if hooks_all else sorted(hooks_set),
            "mcp": "*" if mcp_all else sorted(mcp_set),
        }
        await self._settings.set(
            APPROVALS_KEY, {**self.approvals(), manifest.name: payload}, actor
        )
        # 曾整包批准过:分项覆盖,从整包名单移除(写侧互斥)
        if manifest.name in self.approved_names():
            names = [n for n in self.approved_names() if n != manifest.name]
            await self._settings.set(APPROVED_KEY, names, actor)
        # A4 去勾回收:原勾选 − 现勾选的 mcp id,按与撤销相同的安全链处理
        reclaimed, reclaim_skipped = await self._reclaim_mcp_servers(
            name, manifest,
            self._mcp_selected_ids(name, manifest, old)
            - self._mcp_selected_ids(name, manifest, approval),
            actor,
        )
        return {
            **self._approval_result(manifest.name, loaded, registered, mcp_reg_skipped),
            "skipped": skipped,
            "granularity": "item",
            "mcp_reclaimed": reclaimed,
            "mcp_reclaim_skipped": reclaim_skipped,
        }

    async def unapprove(self, name: str, actor: ActorRef) -> dict:
        """撤销(整包或分项都走这里):清两键名单 + 热卸 + 按安全规则回收登记的 MCP。

        插件目录可能已被删(名单残留):撤销仍须清名单,否则死条目永远清不掉;
        清单在就照常热卸,不在则跳过热卸(unloaded 计 0)。MCP 回收(phase-76,
        选型 S3)只动「本插件登记过且未批准任何工具」的条目,其余跳过披露。
        """
        manifest = self.find(name)
        approval = self._approval_of(manifest) if manifest is not None else None
        unloaded = self._unload_manifest(manifest) if manifest else {"skills": 0, "hooks": 0}
        reclaimed, reclaim_skipped = await self._reclaim_mcp_servers(
            name, manifest, self._mcp_selected_ids(name, manifest, approval), actor
        )
        names = [n for n in self.approved_names() if n != name]
        await self._settings.set(APPROVED_KEY, names, actor)
        if name in self.approvals():
            await self._clear_approvals(name, actor)
        return {
            "name": name,
            "approved": False,
            "loaded": {"skills": [], "hooks": 0, "mcp_registered": 0, "mcp_skipped": False},
            "unloaded": unloaded,
            "skipped": {"skills": [], "hooks": [], "mcp": []},
            "mcp_reclaimed": reclaimed,
            "mcp_reclaim_skipped": reclaim_skipped,
        }

    # ---- 内部 ----

    def _approval_result(
        self, name: str, loaded: dict, registered: int, mcp_skipped: bool
    ) -> dict:
        """批准成功返回:72 loaded 契约 + 顶层 skipped(分项未知名披露)。"""
        return {
            "name": name,
            "approved": True,
            "loaded": {**loaded, "mcp_registered": registered, "mcp_skipped": mcp_skipped},
            "skipped": {"skills": [], "hooks": [], "mcp": []},
        }

    def _skipped_for(self, manifest: PluginManifest, approval: Approval) -> dict:
        """勾了但清单当前没有的条目:跳过不装,返回披露(持久化不改写)。"""
        valid_skills = {sname for _d, sname in manifest_skill_entries(manifest)}
        valid_hooks = {rel for _p, rel in manifest_hook_entries(manifest)}
        valid_mcp = set(manifest_mcp_servers(manifest))
        return {
            "skills": sorted(approval.skills - valid_skills),
            "hooks": sorted(approval.hooks - valid_hooks),
            "mcp": sorted(approval.mcp - valid_mcp),
        }

    async def _clear_approvals(self, name: str, actor: ActorRef) -> None:
        approvals = dict(self.approvals())
        approvals.pop(name, None)
        await self._settings.set(APPROVALS_KEY, approvals, actor)

    def _require(self, name: str) -> PluginManifest:
        manifest = self.find(name)
        if manifest is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"没有这个插件: {name}")
        return manifest

    def _declared_ons(self, manifest: PluginManifest) -> set[str]:
        """插件 hook 文件声明的 on 集合(坏文件跳过;生命周期点与事件类型都算)。"""
        ons: set[str] = set()
        for hook_path, _rel in manifest_hook_entries(manifest):
            on = _hook_on(hook_path)
            if on:
                ons.add(on)
        return ons

    def _pattern_still_wanted(self, name: str, pattern: str) -> bool:
        """其他已批准插件是否真的会装载声明该 pattern 的 hook(有则不撤订阅)。

        整包(hooks_all)或分项勾选了声明该 pattern 的 hook 文件才算「仍被需要」;
        只看「manifest 声明过」不够——分项插件没勾那个文件时它并没注册,若因
        它保留订阅会让被撤插件的 pattern 悬空在 event_patterns 里(自审修正)。
        """
        for other in self.manifests():
            if other.name == name:
                continue
            approval = self._approval_of(other)
            if approval is None:
                continue
            for hook_path, rel in manifest_hook_entries(other):
                if _hook_on(hook_path) == pattern and (
                    approval.hooks_all or rel in approval.hooks
                ):
                    return True
        return False

    def _mcp_still_wanted(self, name: str, sid: str) -> bool:
        """其他已批准插件是否仍需要该 mcp server id(A5;_pattern_still_wanted 同精神)。

        「仍需要」= 其他插件已批准、其 mcp.json 声明了该 id,且(整包 mcp_all
        或分项勾了该 id);只声明但没勾的不算,与 74 分项装载语义一致。
        """
        for other in self.manifests():
            if other.name == name:
                continue
            approval = self._approval_of(other)
            if approval is None:
                continue
            if sid in manifest_mcp_servers(other) and (
                approval.mcp_all or sid in approval.mcp
            ):
                return True
        return False

    def _mcp_selected_ids(
        self, name: str, manifest: PluginManifest | None, approval: Approval | None
    ) -> set[str]:
        """该插件按当前审批实际登记过的 mcp server id(A1/A2 判定,写回钉死)。

        manifest 在场:声明集 ∩ 审批勾选(整包 mcp_all = 全部声明,分项取勾选
        且仍需在声明集内);目录已删(B4):退化为审批记录 approvals[name].mcp
        的 id 列表——"*" 或整包旧键没有 id 记录,无法判定归属,返回空集不回收。
        """
        if manifest is not None:
            if approval is None:
                return set()
            declared = set(manifest_mcp_servers(manifest))
            return declared if approval.mcp_all else (set(approval.mcp) & declared)
        raw = self.approvals().get(name)
        mcp_raw = raw.get("mcp") if isinstance(raw, dict) else None
        if not isinstance(mcp_raw, list):
            return set()
        return {str(x) for x in mcp_raw if str(x).strip()}

    async def _reclaim_mcp_servers(
        self,
        name: str,
        manifest: PluginManifest | None,
        selected: set[str],
        actor: ActorRef,
    ) -> tuple[list[str], list[dict]]:
        """按安全链回收候选 mcp server(phase-76,选型 S3);返回 (回收 id, 跳过披露)。

        候选 = selected ∩ 当前 agent.mcp.servers;逐条过安全链,任一不满足跳过
        并披露 reason,绝不静默误删(A2):
        - 配置匹配守卫(manifest 在场):当前配置须与插件 mcp.json 声明经同一
          归一变换后一致——同 id 但用户手工添加过不同参数的不回收;
        - 其他已批准插件仍需要(A5)不回收;
        - 工具已被批准(S3)不回收:用户显式依赖,保留并可在外接 MCP 手动移除。
        回收路径与 remove_mcp_server 等价(A3):unmount + drop_session +
        delete_config;单台失败(C3)记入 skipped,不回滚撤销、不影响其余条目。
        """
        if self._mcp is None or not selected:
            return [], []
        declared = manifest_mcp_servers(manifest) if manifest is not None else {}
        reclaimed: list[str] = []
        skipped: list[dict] = []
        for sid in sorted(selected):
            try:
                cfg = self._mcp.find_config(sid)
                if cfg is None:
                    skipped.append({"id": sid, "reason": "配置已不存在"})
                    continue
                if manifest is not None:
                    try:
                        expected = _plugin_server_config(sid, declared.get(sid))
                    except ServiceError:
                        # 声明非法(登记时已被跳过,该配置必为手工同 id):诚实跳过,
                        # 不落「回收失败」兜底把有意保留误报成异常
                        skipped.append({
                            "id": sid,
                            "reason": "插件声明无效(登记时已跳过),未回收",
                        })
                        continue
                    if {k: cfg.get(k) for k in expected} != expected:
                        skipped.append({
                            "id": sid,
                            "reason": "配置与插件声明不一致(疑为手工添加),未回收",
                        })
                        continue
                if self._mcp_still_wanted(name, sid):
                    skipped.append({"id": sid, "reason": "其他已批准插件仍在使用"})
                    continue
                if list(cfg.get("approved") or []):
                    skipped.append({
                        "id": sid,
                        "reason": "MCP 工具已批准,已保留;可在「外接 MCP」手动移除",
                    })
                    continue
                self._mcp.unmount(sid)
                await self._mcp.drop_session(sid)
                await self._mcp.delete_config(sid, actor)
                reclaimed.append(sid)
            except Exception as exc:  # noqa: BLE001  # C3:单台回收失败不回滚撤销
                skipped.append({"id": sid, "reason": f"回收失败: {exc}"})
        return reclaimed, skipped

    async def _register_mcp(
        self, manifest: PluginManifest, actor: ActorRef, approval: Approval
    ) -> tuple[int, bool]:
        """按勾选把 mcp.json 的 servers 登记为待批准 MCP 条目(复用 add_mcp_server 语义)。

        整包(mcp_all)或分项勾选的 server id 才登记;缺失 / 空 / 坏文件 →
        (0, True);单条校验失败跳过该条不炸批准;已有同 id 配置(用户手动加过)
        不覆盖。绝不自动批准工具。
        """
        servers = manifest_mcp_servers(manifest)
        if not servers:
            return 0, True
        registered = 0
        for sid, raw in servers.items():
            if not approval.mcp_all and sid not in approval.mcp:
                continue
            try:
                cfg = _plugin_server_config(sid, raw)
            except ServiceError as exc:
                log.warning("插件 %s 的 MCP 条目 %r 跳过: %s", manifest.name, sid, exc)
                continue
            if self._mcp is not None and self._mcp.find_config(cfg["id"]) is None:
                await self._mcp.upsert_config({**cfg, "approved": []}, actor)
                registered += 1
        return registered, False


def _hook_on(hook_path: Path) -> str:
    """hook json 声明的 on;坏文件 → 空串(清单展示跳过,不炸)。"""
    try:
        data = json.loads(hook_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("on") or "") if isinstance(data, dict) else ""


def _hook_enabled(hook_path: Path) -> bool:
    """hook json 是否启用;坏文件 → False。"""
    try:
        data = json.loads(hook_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data.get("enabled", False)) if isinstance(data, dict) else False


def _mcp_tools_approved(mcp: Any, sid: str) -> list[str]:
    """只读既有 MCP 存储的 approved 工具名单(未登记 → 空)。"""
    if mcp is None:
        return []
    cfg = mcp.find_config(sid)
    if cfg is None:
        return []
    approved = cfg.get("approved") or []
    return list(approved) if isinstance(approved, list) else []
