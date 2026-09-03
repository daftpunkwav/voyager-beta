"""用户 hooks 热装热卸(phase-78,§9.13)。

用户在 `workspace/hooks/` 增删改声明式 hook json 后,无需重启即可经
reload() 重载:按 `user:` 前缀卸旧 → 重装目录 → 选择性撤回只由用户侧
声明的领域事件订阅 → 经既有 `EventLoop.sync_extra_patterns` 收敛订阅
(与 PluginManager 注入的同一回调,禁止另起第二套订阅入口)。

选型(写回钉死):
- 触发方式 H1:仅手动 capability(reload_user_hooks)+ 设置页按钮,
  不做文件系统 watch。
- 订阅撤回对标插件语义:某 pattern 只有在「新装载的用户文件不再声明、
  HookRegistry 归属记录里除 `user:` 前缀外无其他已装载 source、且没有
  已批准插件仍需要(PluginManager.pattern_still_wanted)」三条同时成立
  时才 forget,绝不把插件订阅一并摘掉。
- 目录钉死装配时的 workspace/hooks,reload 不接路径参数(防把任意
  路径的 json 当 hook 装载);声明式 only,不执行 json 外脚本。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.hooks.loader import HookLoader
from agent.hooks.triggers import HOOK_POINTS, HookRegistry

log = logging.getLogger("agent.hooks.reload")

#: 用户 hooks 的 source 前缀(与 build_agent 启动装载一致;热卸只摘这层)
USER_SOURCE_PREFIX = "user:"


def _read_hook_json(path: Path) -> dict | None:
    """读单个 hook json;坏文件 / 非 dict → None(调用方按无法解析处理)。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class UserHookReloader:
    """workspace/hooks 用户钩子的重载与只读列举;capability 层入口经它实现。"""

    def __init__(
        self,
        registry: HookRegistry,
        hooks_dir: str | Path,
        *,
        plugins: Any | None = None,  # PluginManager(撤订阅前的插件兜底判定)
    ) -> None:
        self._registry = registry
        self._hooks_dir = Path(hooks_dir)
        self._plugins = plugins
        self._sync: Callable[[tuple[str, ...]], None] | None = None

    def set_subscription_sync(
        self, sync: Callable[[tuple[str, ...]], None] | None
    ) -> None:
        """注入订阅同步回调(build_agent 在 EventLoop 构造后调用)。

        与 PluginManager.set_subscription_sync 同一入口、同一基线语义:
        注入即先同步一次,启动装载阶段的 pattern 不缺账。
        """
        self._sync = sync
        if sync is not None:
            self._sync_subscription()

    def _sync_subscription(self) -> None:
        """把当前 hooks.event_patterns 推给 EventLoop(未注入时 no-op)。"""
        if self._sync is not None:
            self._sync(self._registry.event_patterns)

    def reload(self) -> dict:
        """重载用户 hooks:卸旧(user: 前缀)→ 重装 → 选择性撤订阅 → 同步。

        返回体:`loaded`(本次装载文件数)、`event_patterns`(重载后当前
        全量订阅)、`skipped`(无法解析而跳过的文件及原因)。
        """
        # 1. 重载前用户侧参与声明的 pattern(owner 记录判定;生命周期点不记,
        #    天然不在其中——它们不走订阅)
        old_ons = {
            p for p in self._registry.event_patterns
            if any(
                s.startswith(USER_SOURCE_PREFIX)
                for s in self._registry.pattern_owner_sources(p)
            )
        }
        # 2. 只卸 user: 前缀;插件(plugin:)与其它前缀的注册不动
        self._registry.remove_source(USER_SOURCE_PREFIX)
        # 3. 重装目录下全部 json;单文件坏不炸重载,跳过披露(对标插件装载容错)
        loader = HookLoader(self._registry)
        loaded = 0
        skipped: list[dict] = []
        new_ons: set[Any] = set()  # 镜像 loader 对 on 的宽松取值,可能持非串
        # 目录不存在时 glob 为空:成功、loaded=0、用户钩子已清零(B3),不建目录
        for path in sorted(self._hooks_dir.glob("*.json")):
            # 先读一次并校验,再交给 loader(单次读取;坏文件不进注册表,理由可读)。
            # on 取值与 loader 完全镜像(data.get("on", "") 原样),保证 new_ons
            # 与 registry 实际记录的 pattern 一致
            data = _read_hook_json(path)
            if data is None:
                skipped.append({"path": path.name, "reason": "无法解析(JSON 须为对象)"})
                log.warning("用户 hook 文件无法解析,已跳过: %s", path)
                continue
            try:
                count = loader.load_file(path, source="user", approved=True)
            except Exception as exc:  # noqa: BLE001  # 装载期单文件故障跳过不炸重载
                skipped.append({"path": path.name, "reason": f"装载失败: {exc}"})
                log.warning("用户 hook 文件装载失败,已跳过: %s", path)
                continue
            if count:
                loaded += count
                on = data.get("on", "")
                if on not in HOOK_POINTS:
                    new_ons.add(on)
        # 4. 选择性撤订阅:旧用户 pattern 不再被新文件声明、无其他已装载
        #    source、且没有已批准插件仍需要,三条同时成立才 forget
        #    (key=str:loader 对异常 on 值宽松,history 可能混入非串 pattern)
        for pattern in sorted(old_ons - new_ons, key=str):
            if any(
                not s.startswith(USER_SOURCE_PREFIX)
                for s in self._registry.pattern_owner_sources(pattern)
            ):
                continue
            if self._plugins is not None and self._plugins.pattern_still_wanted(pattern):
                continue
            self._registry.forget_event_pattern(pattern)
        # 5. 订阅收敛(同一 sync 入口;未注入时只改 registry,loop 侧启动装载已带)
        self._sync_subscription()
        return {
            "loaded": loaded,
            "event_patterns": list(self._registry.event_patterns),
            "skipped": skipped,
        }

    def list(self) -> list[dict]:
        """list_user_hooks 数据源:目录下 *.json 的声明与装载状态(只读)。

        `loaded` 以注册表 source(`user:<文件名主干>`)为准;坏文件 on 为
        空、enabled 为 False,loaded 必为 False。
        """
        loaded_sources = set(self._registry.sources)
        items: list[dict] = []
        for path in sorted(self._hooks_dir.glob("*.json")):
            data = _read_hook_json(path)
            items.append(
                {
                    "path": path.name,
                    "on": str(data.get("on") or "") if data else "",
                    "enabled": bool(data.get("enabled", False)) if data else False,
                    "description": str(data.get("description") or path.stem) if data else "",
                    "loaded": f"{USER_SOURCE_PREFIX}{path.stem}" in loaded_sources,
                }
            )
        return items
