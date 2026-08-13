"""思考标记流式拆分单元测试"""
from agent_core.agents.think_stream import (
    THINK_END,
    THINK_START,
    ThinkStreamSplitter,
    split_complete_text,
)


def test_split_complete_with_tags():
    raw = f"{THINK_START}\n先看技术栈\n再看用途\n{THINK_END}\n# 正文\nhello"
    think, body = split_complete_text(raw)
    assert "技术栈" in think
    assert body.startswith("# 正文")


def test_split_complete_without_tags():
    think, body = split_complete_text("直接正文")
    assert think == ""
    assert body == "直接正文"


def test_stream_splitter_incremental():
    s = ThinkStreamSplitter()
    parts = []
    for ch in f"{THINK_START}\nabc\n{THINK_END}\nXYZ":
        parts.extend(s.feed(ch))
    parts.extend(s.flush())
    think = "".join(t for c, t in parts if c == "thinking")
    text = "".join(t for c, t in parts if c == "text")
    assert "abc" in think
    assert "XYZ" in text


def test_stream_splitter_no_tags_all_text():
    s = ThinkStreamSplitter()
    parts = s.feed("hello world")
    parts.extend(s.flush())
    assert all(c == "text" for c, _ in parts)
    assert "".join(t for _, t in parts) == "hello world"
