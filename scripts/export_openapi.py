"""导出 FastAPI OpenAPI JSON 到 packages/contracts（无需起服务）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "services" / "api", ROOT / "services" / "agent"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# 导出时使用占位密钥，避免依赖本地 .env
os.environ.setdefault("SECRET_KEY", "openapi-export-secret-key-32bytes!!")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from api_backend.main import app  # noqa: E402

OUT = ROOT / "packages" / "contracts" / "openapi.json"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
