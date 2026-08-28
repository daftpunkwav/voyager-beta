"""Markdown ATX 标题大纲:与前端 extractNoteToc 同语义。"""

from __future__ import annotations

import re
from typing import Any


def extract_toc(content: str) -> list[dict[str, Any]]:
    """提取 Markdown 标题大纲(1-6 级 ATX):level/text/line(1 基,LF 文本)。

    供前端大纲面板与滚动定位;代码块内的 `#` 注释不是标题——跳过围栏段。
    """
    toc: list[dict[str, Any]] = []
    in_fence = False
    fence_marker = ""
    for line_no, line in enumerate(content.split("\n"), start=1):
        stripped = line.lstrip()
        if stripped[:3] in ("```", "~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            continue
        if in_fence or not stripped.startswith("#"):
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if m:
            toc.append({"level": len(m.group(1)), "text": m.group(2).strip(),
                        "line": line_no})
    return toc
