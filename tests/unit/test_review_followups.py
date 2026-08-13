"""SSE 解析与项目 URL 校验等审查跟进单测"""
import pytest
from agent_core.agents.stream_events import format_sse, parse_sse_chunk
from api_backend.schemas.project import ProjectCreate, ProjectUpdate
from pydantic import ValidationError


def test_parse_sse_chunk_roundtrip():
    frame = format_sse("text_delta", {"content": "你好"}).to_sse()
    parsed = parse_sse_chunk(frame)
    assert parsed is not None
    event, data = parsed
    assert event == "text_delta"
    assert data["content"] == "你好"


def test_parse_sse_chunk_rejects_garbage():
    assert parse_sse_chunk("not-sse") is None
    assert parse_sse_chunk("event: x\ndata: not-json\n\n") is None


def test_project_create_rejects_javascript_url():
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", url="javascript:alert(1)")


def test_project_create_rejects_non_http():
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", url="ftp://example.com/a")


def test_project_create_github_source_requires_github_host():
    with pytest.raises(ValidationError):
        ProjectCreate(
            name="x",
            url="https://evil.example/repo",
            source="github",
        )
    ok = ProjectCreate(
        name="x",
        url="https://github.com/a/b",
        source="github",
    )
    assert ok.url.endswith("/a/b")


def test_project_update_url_http_ok():
    u = ProjectUpdate(url="https://example.com/docs")
    assert u.url == "https://example.com/docs"
