"""本机会话令牌(§7.4):首次启动生成密钥文件,签发/校验 HMAC-SHA256 令牌。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

_DOMAIN = "actor"
_DEFAULT_TTL = 30 * 24 * 3600  # 本机令牌默认 30 天


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class LocalTokenIssuer:
    """签发与校验本机令牌。密钥落盘于 runtime-data(首次启动自动生成,权限 0o600)。"""

    def __init__(self, secret_path: str | Path) -> None:
        self._path = Path(secret_path)
        self._secret = self._load_or_create()

    def _load_or_create(self) -> bytes:
        if self._path.exists():
            return bytes.fromhex(self._path.read_text(encoding="utf-8").strip())
        self._path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_hex(32)
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(secret)
        return bytes.fromhex(secret)

    def issue(self, actor: ActorRef, ttl_seconds: float = _DEFAULT_TTL) -> str:
        payload = {
            "kind": actor.kind.value,
            "id": actor.id,
            "scopes": list(actor.scopes),
            "exp": time.time() + ttl_seconds,
        }
        body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
        sig = _b64e(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def verify(self, token: str) -> ActorRef:
        try:
            body, sig = token.split(".")
            expected = _b64e(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                raise ValueError("签名不匹配")
            payload = json.loads(_b64d(body))
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(_DOMAIN, ErrorSuffix.AUTH_REQUIRED, f"令牌无效: {exc}") from exc
        if float(payload.get("exp", 0)) < time.time():
            raise ServiceError(
                _DOMAIN, ErrorSuffix.AUTH_REQUIRED, "令牌已过期", hint="重新获取本机令牌"
            )
        return ActorRef(
            kind=ActorKind(payload["kind"]),
            id=str(payload["id"]),
            scopes=tuple(payload.get("scopes") or ()),
        )
