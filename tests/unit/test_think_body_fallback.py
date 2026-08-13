"""专家空正文 / THINK 未闭合时，正文不得被吞进思考区"""
from agent_core.agents.react import _strip_think_markers
from agent_core.agents.think_stream import THINK_END, THINK_START, split_complete_text


def test_unclosed_think_becomes_body():
    raw = f"{THINK_START}\n这是本应给用户的讲解全文，很长很长。\n"
    think, body = split_complete_text(raw)
    assert think == ""
    assert "讲解全文" in body


def test_closed_think_splits():
    raw = f"{THINK_START}\n推理要点\n{THINK_END}\n## 正文标题\n内容"
    think, body = split_complete_text(raw)
    assert "推理要点" in think
    assert body.lstrip().startswith("## 正文标题")


def test_strip_think_markers():
    raw = f"{THINK_START}\nabc\n{THINK_END}\ndef"
    assert "abc" in _strip_think_markers(raw)
    assert THINK_START not in _strip_think_markers(raw)
