"""
可选 HTTP sidecar：python -m graph_fallback.server
供独立进程托管（P5 / 大规模索引）。

安全边界（与 C 引擎 http_server.c 的 HTTP 安全门对齐）：
- 仅绑定 127.0.0.1；拒绝非本机 Host 头（防 DNS rebinding）
- POST 要求 Content-Type: application/json（防 form-CSRF 免预检注入）
- index_repository 强制 repo_path 位于 GRAPH_ALLOWED_ROOT 下（越界拒绝）
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .engine import get_engine

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
_MAX_BODY = 10_000_000  # 请求体上限(10MB):防恶意超大 body 耗尽内存


class Handler(BaseHTTPRequestHandler):
    eng = None
    allowed_root: str | None = None

    def log_message(self, fmt: str, *args) -> None:
        return

    def _reject(self, code: int, message: str) -> None:
        self._json(code, {"error": message})

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return False
        hostname = host.rsplit(":", 1)[0].strip("[]")
        return hostname in _LOCAL_HOSTS

    def _content_type_ok(self) -> bool:
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return ctype == "application/json"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._host_allowed():
            self._reject(403, "forbidden")
            return
        eng = Handler.eng
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "engine": "graph-engine"})
            return
        if parsed.path == "/api/layout":
            qs = parse_qs(parsed.query)
            project = (qs.get("project") or [""])[0]
            max_nodes = int((qs.get("max_nodes") or ["5000"])[0])
            self._json(200, eng.fetch_layout(project, max_nodes=max_nodes))
            return
        if parsed.path == "/api/cross-edges":
            self._json(200, {"edges": eng.list_cross_edges()})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._host_allowed():
            self._reject(403, "forbidden")
            return
        if not self._content_type_ok():
            self._reject(415, "unsupported_media_type")
            return
        eng = Handler.eng
        length = int(self.headers.get("Content-Length") or 0)
        if length > _MAX_BODY:
            self._json(413, {"error": "payload_too_large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid_json"})
            return
        if urlparse(self.path).path != "/rpc":
            self._json(404, {"error": "not_found"})
            return
        params = data.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = _dispatch(eng, name, args)
            self._json(200, {"jsonrpc": "2.0", "id": data.get("id"), "result": result})
        except Exception as exc:
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"message": str(exc)},
                },
            )


def _dispatch(eng, name: str, args: dict):
    if name == "index_repository":
        repo_path = args.get("repo_path") or "."
        _assert_within_allowed_root(repo_path)
    # 统一经 GraphEngine.call 分发（与 client._sync_call 共用同一映射）
    return eng.call(name, args)


def _assert_within_allowed_root(repo_path: str) -> None:
    """索引边界强制：repo_path 必须位于 GRAPH_ALLOWED_ROOT 之下，越界拒绝。"""
    root = Handler.allowed_root
    if not root:
        return  # 未配置 allowed_root 时不设边界（与 C 引擎未配置时行为一致）
    root_resolved = Path(root).resolve()
    target = Path(repo_path).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"repo_path 越界：{repo_path} 不在允许根 {root} 之下")


def main() -> None:
    # 引擎层统一读 ENGINE_*(与 C 引擎 getenv 单一权威名一致)；
    # GRAPH_* 是应用层配置契约,由启动器(start-graph-engine.ps1/.sh)翻译。
    root = os.environ.get("ENGINE_ALLOWED_ROOT")
    port = int(os.environ.get("ENGINE_PORT") or "9750")
    Handler.eng = get_engine(data_root=root)
    Handler.allowed_root = root
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"graph-engine listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
