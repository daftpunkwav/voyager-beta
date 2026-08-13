"""共享 Pydantic schemas —— 项目数据契约(ImportRepoItem)。"""
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


class ImportRepoItem(BaseModel):
    owner: str
    repo: str
    url: str

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        """仅允许公开的 HTTPS URL，且域名需在白名单内。"""
        parsed = urlparse(v)
        if parsed.scheme != "https":
            raise ValueError("仅支持 https 协议")
        host = (parsed.hostname or "").lower()
        if not host or host != "github.com":
            raise ValueError("仅支持 github.com 域名")
        return v
