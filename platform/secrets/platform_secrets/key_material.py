"""密钥材料:SECRETS_ENCRYPTION_KEY → SECRET_KEY → 仓库根 .env 兜底(§7.7)。

修订自旧 agent_core/llm/config.py 的 _key_material():
- 去掉 lru_cache(密钥材料允许显式重载,测试可注入);
- 环境变量优先,.env 只作兜底且不覆盖环境;
- 返回空串时由调用方决定是否拒绝服务(BYOK 下无材料则 secret 不可用)。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

ENV_PRIMARY = "SECRETS_ENCRYPTION_KEY"
ENV_FALLBACK = "SECRET_KEY"

_MIN_MATERIAL_LEN = 16

log = logging.getLogger("platform.secrets")


def _pick(enc_key: str | None, secret_key: str | None) -> str:
    custom = (enc_key or "").strip()
    return custom if custom else (secret_key or "").strip()


def load_key_material(env_file: str | Path | None = None) -> str:
    """加载密钥材料。env_file 显式传入时优先于默认的仓库根 .env 探测。

    材料过短(<16 字符)时打告警不拒服务:BYOK 下拒服务会让既有用户突然
    全部 secret 不可用;告警提示用户更换更强的材料。
    """
    material = _pick(os.environ.get(ENV_PRIMARY), os.environ.get(ENV_FALLBACK))
    if not material:
        path = Path(env_file) if env_file else _repo_env()
        material = _read_from_env_file(path)
    if material and len(material) < _MIN_MATERIAL_LEN:
        log.warning(
            "密钥材料仅 %d 字符(建议 ≥%d):Fernet 派生强度不足,请设置更长的"
            " %s / %s", len(material), _MIN_MATERIAL_LEN, ENV_PRIMARY, ENV_FALLBACK,
        )
    return material


def _read_from_env_file(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == ENV_PRIMARY:
            return value.strip().strip('"').strip("'")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and line.partition("=")[0].strip() == ENV_FALLBACK:
            return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


def _repo_env() -> Path | None:
    """本包位于 platform/secrets/platform_secrets/,上三级即仓库根。

    限制:依赖仓库布局(editable/源码运行);非源码形态(如 sdist 安装到
    site-packages)会定位到错误的"仓库根",找不到 .env 时返回空材料由
    调用方降级处理——这是已知且接受的本地工具假设。
    """
    root = Path(__file__).resolve().parents[3]
    return root / ".env"
