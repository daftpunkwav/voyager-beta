"""office 聚合注册表(§6.4/§8.6):仅合并 doc/slides 子模块注册表,零逻辑。"""

from __future__ import annotations

from dataclasses import dataclass

from platform_capability import Registry
from platform_eventbus import EventBus

from .modules.doc import capabilities as doc_caps
from .modules.doc.capabilities import DocDeps
from .modules.slides import capabilities as slides_caps
from .modules.slides.capabilities import SlidesDeps
from .store import DocumentStore

registry = Registry("office")
registry.merge(doc_caps.registry, slides_caps.registry)


@dataclass
class OfficeDeps:
    """聚合层统一装配的子模块依赖。"""

    store: DocumentStore
    bus: EventBus | None


def init_all(deps: OfficeDeps) -> None:
    doc_caps.init_deps(DocDeps(store=deps.store, bus=deps.bus))
    slides_caps.init_deps(SlidesDeps(store=deps.store, bus=deps.bus))
