"""密钥保管(§7.7):加密落盘、按需分发。secret 的唯一写入口是用户本人(§8.8)。"""

from platform_secrets.key_material import load_key_material
from platform_secrets.store import SecretStore, SecretUnavailableError

__all__ = ["SecretStore", "SecretUnavailableError", "load_key_material"]
