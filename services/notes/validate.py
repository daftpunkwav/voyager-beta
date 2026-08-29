"""笔记字段校验:标题 / 正文长度 / 标签字符。"""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError

from .runtime import DOMAIN

MAX_TITLE = 200
MAX_CONTENT = 200_000
MAX_IMPORT_BYTES = MAX_CONTENT * 4
MAX_SOURCE_ID = 80
TAG_FORBIDDEN = '"\\,[]'


def validate_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "标题不能为空")
    if len(title) > MAX_TITLE:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"标题过长(≤{MAX_TITLE} 字)")
    return title


def validate_content(content: str | None) -> None:
    if content is not None and len(content) > MAX_CONTENT:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"正文过长(≤{MAX_CONTENT} 字符)")


def validate_tag(tag: str) -> str:
    tag = (tag or "").strip()
    if not tag or any(ch in TAG_FORBIDDEN for ch in tag):
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           f"标签为空或含非法字符({TAG_FORBIDDEN}): {tag!r}")
    if len(tag) > 32:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "标签过长(≤32 字)")
    return tag


def validate_source_id(source_id: str) -> str:
    """source_id 与 node_id 只允许安全标识符,禁止路径穿越字符。"""
    sid = str(source_id or "").strip()
    if not sid:
        return ""
    if "/" in sid or "\\" in sid or ".." in sid or len(sid) > MAX_SOURCE_ID:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT,
                           "source_id 或 node_id 非法")
    return sid


def validate_node_id(node_id: str) -> str:
    return validate_source_id(node_id)
