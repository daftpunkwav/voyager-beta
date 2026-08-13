"""报错码三方同步：ERROR_CODES.md ↔ error_codes.py ↔ errorCodes.ts。"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _codes_from_md(text: str) -> set[str]:
    # 表行登记码：| `DOMAIN_REASON` | —— 至少含一个下划线，排除域前缀表
    return set(re.findall(r"\|\s*`([A-Z][A-Z0-9]*_[A-Z0-9_]+)`\s*\|", text))


def _codes_from_ts(text: str) -> set[str]:
    # ERROR_CODES 对象顶层键
    m = re.search(r"export const ERROR_CODES[^=]*=\s*\{([\s\S]*?)\n\};", text)
    assert m, "未找到 ERROR_CODES 对象"
    return set(re.findall(r"^\s{2}([A-Z][A-Z0-9_]+)\s*:", m.group(1), re.M))


def test_error_codes_python_ts_md_in_sync():
    from api_backend.core.error_codes import ALL_ERROR_CODES

    md = (REPO_ROOT / "docs/architecture/decoupling/ERROR_CODES.md").read_text(
        encoding="utf-8"
    )
    ts = (REPO_ROOT / "apps/web/src/utils/errorCodes.ts").read_text(encoding="utf-8")

    # 文档「弃用」表含旧码，只比对登记表正文
    md_main = md.split("## 弃用", 1)[0]
    md_codes = _codes_from_md(md_main)
    ts_codes = _codes_from_ts(ts)
    py_codes = set(ALL_ERROR_CODES)

    assert py_codes == ts_codes, (
        f"Python 有而 TS 无: {sorted(py_codes - ts_codes)}; "
        f"TS 有而 Python 无: {sorted(ts_codes - py_codes)}"
    )
    assert py_codes == md_codes, (
        f"Python 有而 MD 无: {sorted(py_codes - md_codes)}; "
        f"MD 有而 Python 无: {sorted(md_codes - py_codes)}"
    )
