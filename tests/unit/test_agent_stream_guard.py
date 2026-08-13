"""会话级 SSE 流控单元测试"""
from uuid import uuid4

from agent_runtime.execution import (
    _begin_session_stream,
    _end_session_stream,
    _session_stream_cancel,
)


def test_begin_session_stream_cancels_previous():
    sid = uuid4()
    first = _begin_session_stream(sid)
    assert not first.is_set()
    second = _begin_session_stream(sid)
    assert first.is_set()
    assert not second.is_set()
    assert _session_stream_cancel[sid] is second
    _end_session_stream(sid, second)
    assert sid not in _session_stream_cancel


def test_end_session_stream_ignores_stale_event():
    sid = uuid4()
    first = _begin_session_stream(sid)
    second = _begin_session_stream(sid)
    _end_session_stream(sid, first)  # 旧事件不应清掉新流
    assert _session_stream_cancel[sid] is second
    _end_session_stream(sid, second)
    assert sid not in _session_stream_cancel
