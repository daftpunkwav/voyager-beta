"""
Pydantic schemas —— 本机身份（无认证）

UserOut 仅描述本机展示名与 GitHub 绑定状态；无头像 / 邮箱 / 密码。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserOut(BaseModel):
    """本机身份；id 固定为字符串 local（非 UUID）。"""

    id: str
    username: str
    github_login: Optional[str] = None
    github_bound: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
