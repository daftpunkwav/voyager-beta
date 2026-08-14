"""上下文装配(§9.12):规则 → 人格 → 画像 → 任务书 → subagent 摘要 → 页面摘要。

注入的是各层的**摘要**;全文经 OnDemandLoader 按需加载(§9.20)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.context.pages import PageContextRegistry
from agent.memory import Memory
from agent.personas import Persona

if TYPE_CHECKING:  # 仅类型标注;运行期 duck type,避免环导入
    from agent.subagent.instance import TaskBook


class ContextBuilder:
    def __init__(
        self,
        *,
        rules: list[str] | None = None,
        memory: Memory | None = None,
        digests: Any = None,  # DigestStore(避免环依赖,duck type: render())
        pages: PageContextRegistry | None = None,
    ) -> None:
        self._rules = list(rules or [])
        self._memory = memory
        self._digests = digests
        self._pages = pages

    def system(
        self,
        *,
        persona: Persona | None = None,
        task: TaskBook | None = None,
        style: str = "",
    ) -> str:
        layers: list[str] = []
        if self._rules:
            layers.append("【全局规则】\n" + "\n".join(f"- {r}" for r in self._rules))
        if persona is not None:
            layers.append(
                f"【人格】{persona.display_name}({persona.style})\n{persona.system_prompt}"
            )
        if style:
            layers.append(f"【风格】{style}")
        if self._memory is not None:
            layers.append("【用户画像】\n" + self._memory.profile.render())
        if task is not None and task.goal:
            block = f"【任务书】目标: {task.goal}"
            if task.constraints:
                block += f"\n约束: {task.constraints}"
            if task.done_when:
                block += f"\n完成判定: {task.done_when}"
            layers.append(block)
        if self._digests is not None:
            rendered = self._digests.render()
            if rendered:
                layers.append("【进行中的 subagent】\n" + rendered)
        if self._pages is not None:
            layers.append("【用户当前页面】\n" + self._pages.render())
        return "\n\n".join(layers)

    def messages(
        self, system: str, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [{"role": "system", "content": system}, *history]
