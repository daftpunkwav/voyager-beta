"""人格能力面回归(铁律 6):白名单与提示词点名必须双向对齐真工具面。

- tool_allow 精确名都要在聚合 Toolbelt 里真实存在(拼写/改名即红);
- 前缀条目(phase-06,如 notes__*)必须在名册中至少匹配一个真工具(死前缀即红);
- 提示词点名的每个工具名都要被白名单覆盖(精确名或前缀展开);
  Lucien 不裁剪,只查点名非假名。
聚合装配是工具面真相:内部工具 + 领域桥(deploy/bridge.py)注入的 {domain}__*。
"""

from pathlib import Path

from agent.personas import PERSONAS
from deploy.backend import build


def _allow_covers(allow: tuple[str, ...] | None, tool: str) -> bool:
    """白名单是否覆盖某工具:精确名命中或前缀条目展开命中。"""
    if allow is None:
        return True
    return any(
        t == tool or (t.endswith("*") and len(t) > 1 and tool.startswith(t[:-1]))
        for t in allow
    )


def _persona_tool_audit(agent_app) -> list[str]:
    real = set(agent_app.spawner._toolbelt.names())
    problems: list[str] = []
    for key, persona in PERSONAS.items():
        allow = persona.tool_allow or ()
        problems += [
            f"{key}: 白名单死名 {t}" for t in allow
            if not t.endswith("*") and t not in real
        ]
        problems += [
            f"{key}: 死前缀(名册中无匹配) {t}" for t in allow
            if t.endswith("*") and len(t) > 1
            and not any(n.startswith(t[:-1]) for n in real)
        ]
        mentioned = sorted(t for t in real if t in persona.system_prompt)
        if persona.tool_allow is None:
            problems += [
                f"{key}: 点名假工具 {t}" for t in mentioned if t not in real
            ]
            continue
        problems += [
            f"{key}: 提示词点名但不在白名单 {t}"
            for t in mentioned if not _allow_covers(persona.tool_allow, t)
        ]
        # 「提示词未点名」只对精确名条目检查:前缀展开是动态名册,不逐个点名
        problems += [
            f"{key}: 白名单死工具(提示词未点名) {t}"
            for t in allow
            if not t.endswith("*") and t not in mentioned
        ]
    return problems


def test_persona_tool_allow_matches_toolbelt(tmp_path: Path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    try:
        problems = _persona_tool_audit(app.state.backend.agent)
    finally:
        app.state.backend.agent.close()
    assert problems == []
