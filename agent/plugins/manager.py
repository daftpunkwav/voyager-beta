"""插件发现与整包批准(§9.13,phase-72)。

插件 = 插件根目录下一个子目录,含声明式清单 plugin.json(样例 plugins/_example):
skills 指向 SKILL.md 目录、hooks 指向 hook json、mcp 指向外接 MCP 配置。
声明式 only:插件不 import 平台实现、不执行任意代码;装载顺序是
发现(list 可见)→ 用户整包批准 → skill 进 SkillLoader roots / hook 进
HookRegistry / MCP 只登记待批准条目(不自动 approve_mcp_tools)。

选型(写回钉死):
- `_` 前缀目录(如 `_example`)**照常被 list 看到**,与其他插件同规则——
  未批准一律不装载;`_` 前缀只是「示例/未完成」的命名约定,不是加载器跳过逻辑。
- 批准名单持久化在设置键 `agent.plugins.approved`(list[str],user_only)。
- contains 路径 jail:声明相对路径 resolve 后必须仍在插件目录内(拒 `../` 逃逸)。
"""

from __future__ import annotations

import json
import logging
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


def manifest_skills(manifest: PluginManifest) -> list[Path]:
    """contains.skills 中真实存在 SKILL.md 的目录(jail 之外的条目丢弃)。"""
    out: list[Path] = []
    for rel in _items(manifest.contains.get("skills")):
        path = resolve_within(manifest.path, rel)
        if path is not None and (path / "SKILL.md").is_file():
            out.append(path)
    return out


def manifest_hook_dirs(manifest: PluginManifest) -> list[Path]:
    """contains.hooks 中真实存在的 hook 文件的父目录(去重;装载粒度是目录)。"""
    out: list[Path] = []
    for rel in _items(manifest.contains.get("hooks")):
        path = resolve_within(manifest.path, rel)
        if path is not None and path.is_file():
            parent = path.parent
            if parent not in out:
                out.append(parent)
    return out


def manifest_mcp(manifest: PluginManifest) -> Path | None:
    """contains.mcp 指向且真实存在的 mcp.json 路径;未声明 / 缺文件 → None。"""
    path = resolve_within(manifest.path, manifest.contains.get("mcp"))
    if path is not None and path.is_file():
        return path
    return None


def skill_names_in(skill_dir: Path) -> list[str]:
    """目录下的 skill 名(与 SkillLoader._scan 同规则:SKILL.md 的父目录名)。"""
    return [p.parent.name for p in sorted(skill_dir.rglob("SKILL.md"))]


class PluginManager:
    """发现 + 批准名单 + 装载/热卸;capability 层经它实现 list/批准两能力。"""

    def __init__(
        self,
        root: str | Path,
        *,
        settings: Any,  # SettingsStore(读/写 agent.plugins.approved)
        skills: SkillLoader,
        hooks: HookRegistry,
        mcp: Any | None = None,  # McpClientPool(批准时登记 MCP 条目;可省)
    ) -> None:
        self._root = Path(root)
        self._settings = settings
        self._skills = skills
        self._hooks = hooks
        self._mcp = mcp

    # ---- 发现与清单形状(list_plugins 数据源) ----

    def manifests(self) -> list[PluginManifest]:
        return discover(self._root)

    def find(self, name: str) -> PluginManifest | None:
        return next((m for m in self.manifests() if m.name == name), None)

    def approved_names(self) -> list[str]:
        value = self._settings.get(APPROVED_KEY)
        if not isinstance(value, list):
            return []
        return [str(n) for n in value]

    def list(self) -> list[dict]:
        """list_plugins items:稳定形状见 phase-72 契约(测试钉死)。"""
        approved = set(self.approved_names())
        items = []
        for m in self.manifests():
            skills = manifest_skills(m)
            hook_files = sum(1 for d in manifest_hook_dirs(m) for _ in d.glob("*.json"))
            items.append(
                {
                    "name": m.name,
                    "version": m.version,
                    "description": m.description,
                    "approved": m.name in approved,
                    "permissions": {
                        "scopes": [str(s) for s in _items(m.permissions.get("scopes"))],
                        "network": str(m.permissions.get("network") or ""),
                        "fs": str(m.permissions.get("fs") or ""),
                    },
                    "contains": {
                        "skills": len(skills),
                        "hooks": hook_files,
                        "mcp": manifest_mcp(m) is not None,
                    },
                    "path": m.path.name,
                }
            )
        return items

    # ---- 装载 / 热卸(build_agent 启动与批准动作共用) ----

    def apply(self, name: str) -> dict:
        """装载已批准插件的 skill 目录与 hook 目录;返回 loaded 计数。MCP 只在批准动作登记。

        先热卸再装载(幂等):重复批准 / 批准重试不会重复注册 hook、重复加 skill root。
        """
        manifest = self._require(name)
        self._unload_manifest(manifest)
        skill_names: list[str] = []
        for skill_dir in manifest_skills(manifest):
            self._skills.add_root(skill_dir)
            skill_names.extend(skill_names_in(skill_dir))
        hook_count = 0
        loader = HookLoader(self._hooks)
        for hook_dir in manifest_hook_dirs(manifest):
            try:
                hook_count += loader.load_dir(
                    hook_dir, source=f"plugin:{manifest.name}", approved=True
                )
            except Exception:  # noqa: BLE001  # 单目录坏 json 不炸批准;记日志披露,计数为 0
                log.warning("插件 %s 的 hook 目录装载失败: %s", manifest.name, hook_dir)
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
        return {"skills": removed_skills, "hooks": removed_hooks}

    # ---- 批准 / 撤销(capability 层入口;actor 落审计) ----

    async def approve(self, name: str, actor: ActorRef) -> dict:
        manifest = self._require(name)
        loaded = self.apply(manifest.name)
        registered, skipped = await self._register_mcp(manifest, actor)
        names = self.approved_names()
        if manifest.name not in names:
            await self._settings.set(APPROVED_KEY, sorted([*names, manifest.name]), actor)
        return {
            "name": manifest.name,
            "approved": True,
            "loaded": {**loaded, "mcp_registered": registered, "mcp_skipped": skipped},
        }

    async def unapprove(self, name: str, actor: ActorRef) -> dict:
        # 插件目录可能已被删(名单残留):撤销仍须清名单,否则死条目永远清不掉;
        # 清单在就照常热卸,不在则跳过热卸(unloaded 计 0)
        manifest = self.find(name)
        unloaded = self._unload_manifest(manifest) if manifest else {"skills": 0, "hooks": 0}
        names = [n for n in self.approved_names() if n != name]
        await self._settings.set(APPROVED_KEY, names, actor)
        return {
            "name": name,
            "approved": False,
            "loaded": {"skills": [], "hooks": 0, "mcp_registered": 0, "mcp_skipped": False},
            "unloaded": unloaded,
        }

    # ---- 内部 ----

    def _require(self, name: str) -> PluginManifest:
        manifest = self.find(name)
        if manifest is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"没有这个插件: {name}")
        return manifest

    def _declared_ons(self, manifest: PluginManifest) -> set[str]:
        """插件 hook 文件声明的 on 集合(坏文件跳过;生命周期点与事件类型都算)。"""
        ons: set[str] = set()
        for hook_dir in manifest_hook_dirs(manifest):
            for hook_path in hook_dir.glob("*.json"):
                try:
                    on = json.loads(hook_path.read_text(encoding="utf-8")).get("on")
                except (OSError, ValueError):
                    continue
                if isinstance(on, str):
                    ons.add(on)
        return ons

    def _pattern_still_wanted(self, name: str, pattern: str) -> bool:
        """其他已批准插件是否也声明同一事件 pattern(有则不撤订阅,防误伤其 hook)。"""
        approved = set(self.approved_names())
        for other in self.manifests():
            if other.name == name or other.name not in approved:
                continue
            if pattern in self._declared_ons(other):
                return True
        return False

    async def _register_mcp(self, manifest: PluginManifest, actor: ActorRef) -> tuple[int, bool]:
        """把 mcp.json 的 servers 登记为待批准 MCP 条目(复用 add_mcp_server 语义)。

        缺失 / 空 / 坏 → (0, True);单条校验失败跳过该条不炸批准;
        已有同 id 配置(用户手动加过)不覆盖。绝不自动批准工具。
        """
        mcp_path = manifest_mcp(manifest)
        if mcp_path is None:
            return 0, True
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0, True
        servers = data.get("servers") if isinstance(data, dict) else None
        if not isinstance(servers, dict) or not servers:
            return 0, True
        registered = 0
        for sid, raw in servers.items():
            entry = dict(raw) if isinstance(raw, dict) else {}
            entry["id"] = str(sid)
            entry.setdefault("kind", "url" if entry.get("url") else "stdio")
            try:
                cfg = validate_server_config({**entry, "approval": "item"})
            except ServiceError as exc:
                log.warning("插件 %s 的 MCP 条目 %r 跳过: %s", manifest.name, sid, exc)
                continue
            if self._mcp is not None and self._mcp.find_config(cfg["id"]) is None:
                await self._mcp.upsert_config({**cfg, "approved": []}, actor)
                registered += 1
        return registered, False
