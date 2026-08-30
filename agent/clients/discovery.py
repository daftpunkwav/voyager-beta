"""服务发现(§9.13 骨架):启动时按 services/*/service.json 读模块卡。

单体形态下领域工具已经走 deploy/bridge.py 的 capability 桥;本模块只做
**发现**(读卡不连接),供 11b 外接 MCP 使用。缺卡/坏卡的目录跳过,不炸启动。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("agent.clients.discovery")


def discover_services(root: str | Path) -> list[dict]:
    """扫 root 下每个服务目录的 service.json,返回解析后的模块卡列表。

    - 跳过下划线开头目录(如 _template);
    - 没有 service.json 或解析失败的目录跳过并记日志;
    - 结果按目录名排序,稳定可测。
    """
    root = Path(root)
    out: list[dict] = []
    if not root.exists():
        return out
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        card = child / "service.json"
        if not card.exists():
            log.debug("跳过无 service.json 的目录: %s", child.name)
            continue
        try:
            data = json.loads(card.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("service.json 解析失败,跳过: %s", card)
            continue
        if not isinstance(data, dict):
            log.warning("service.json 不是对象,跳过: %s", card)
            continue
        data.setdefault("name", child.name)
        out.append(data)
    return out
