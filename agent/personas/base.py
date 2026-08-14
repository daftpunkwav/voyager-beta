"""人格预设(§9.3):纯数据。人格与风格正交;能力面模板供派出时裁剪。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    key: str
    display_name: str
    style: str  # 风格(热心/毒舌/严谨…,§9.14)
    system_prompt: str
    default_mode: str = "react"
    tool_allow: tuple[str, ...] | None = None  # 能力面模板;None=不裁剪
