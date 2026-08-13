"""出站 URL 安全校验 —— 防止 SSRF（含保存时与出站前二次 DNS 校验）

权威实现在 py_shared.security.url_safety，此处 re-export 兼容既有 import。
"""
from py_shared.security.url_safety import (  # noqa: F401
    assert_safe_outbound_https_url,
    is_blocked_ip,
    validate_public_https_url,
)

__all__ = [
    "assert_safe_outbound_https_url",
    "is_blocked_ip",
    "validate_public_https_url",
]
