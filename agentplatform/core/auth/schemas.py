"""认证 API 请求/响应模型(设计 005 §2)。

响应不含 password_hash;错误走统一 {error: {code, message}} 信封。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agentplatform.core.auth.model import UserRole

# 邮箱不做强格式校验(MVP 不引入 email-validator),仅按长度/必填约束。


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=6)
    role: UserRole = UserRole.user


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    """用户对外视图(不含密码哈希)。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    created_at: datetime


class TokenOut(BaseModel):
    token: str
    user: UserOut