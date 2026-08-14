"""上下文工程:装配、压缩、页面感知、按需加载。"""

from agent.context.builder import ContextBuilder
from agent.context.compressor import compress, estimate_tokens
from agent.context.loader import OnDemandLoader
from agent.context.pages import PageContextRegistry, PageSummary

__all__ = [
    "ContextBuilder",
    "OnDemandLoader",
    "PageContextRegistry",
    "PageSummary",
    "compress",
    "estimate_tokens",
]
