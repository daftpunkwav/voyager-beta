"""响应包装单元测试"""
from api_backend.core.responses import meta_ts, wrap_data, wrap_paginated


def test_meta_ts_has_millisecond_timestamp():
    meta = meta_ts()
    assert "ts" in meta
    assert meta["ts"] > 1_700_000_000_000


def test_wrap_data_includes_meta():
    resp = wrap_data({"ok": True})
    assert resp.data == {"ok": True}
    assert "ts" in resp.meta


def test_wrap_paginated_shape():
    resp = wrap_paginated(["a"], total=1, page=1, page_size=20)
    assert resp.data.items == ["a"]
    assert resp.data.total == 1
    assert resp.meta["total"] == 1
