"""hook 加载(§9.13):从插件目录载入声明式 hook(json)。

声明式 hook 只有元信息(on/description/enabled),动作默认为"记录日志";
可执行动作由 Python API register() 提供。插件带入的 hook 经用户批准后启用。

`on` 的两种含义(phase-11):
- 取值 ∈ HOOK_POINTS:生命周期点,直接注册;
- 否则视为**领域事件类型**(如 note.created,支持 fnmatch 通配),
  包装成 on_event 过滤器注册——不必把事件名塞进 HOOK_POINTS 元组。
"""

from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path

from agent.hooks.triggers import HOOK_POINTS, HookRegistry

log = logging.getLogger("agent.hooks.loader")


class HookLoader:
    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry

    def load_dir(self, hooks_dir: str | Path, *, source: str, approved: bool) -> int:
        """载入目录下全部 *.json hook;approved=False 时跳过(等用户批准)。"""
        if not approved:
            return 0
        count = 0
        for path in sorted(Path(hooks_dir).glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("enabled", False):
                continue
            on = data.get("on", "")
            desc = data.get("description", path.stem)
            src = f"{source}:{path.stem}"

            if on in HOOK_POINTS:
                async def _log_only(_desc: str = desc, **kwargs) -> None:
                    log.info("declarative hook 触发: %s (%s)", _desc, kwargs)

                self._registry.register(on, _log_only, source=src)
            else:
                async def _on_event_hook(
                    event, _pattern: str = on, _desc: str = desc, **_kwargs
                ) -> None:
                    """领域事件过滤器:事件类型匹配(支持通配)才记日志。"""
                    etype = str(getattr(event, "type", ""))
                    if fnmatch.fnmatchcase(etype, _pattern):
                        log.info("declarative hook 触发: %s (%s)", _desc, etype)

                self._registry.register("on_event", _on_event_hook, source=src)
            count += 1
        return count
