"""页面上下文主动上报能力。"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="report_page_context", description="页面上报:前端 provider 推送页面摘要(§10.12)")
    def report_page_context(
        page: str, summary: str, counts: dict | None = None, selected: str = ""
    ) -> dict:
        item = deps.pages.update(page, summary, counts=counts, selected=selected)
        return {"page": item.page, "ok": True}
