"""API key 可逆加密(MVP):Fernet,密钥从 SECRET_KEY 派生。

设计 004 要求 api_key_enc 加密存储;生产环境 SECRET_KEY 必须由环境变量注入,
换取明文需持有该密钥。
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from agentplatform.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    """加密 API key,返回密文。"""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """解密密文;密钥错误/密文损坏时抛 InvalidToken。"""
    return _fernet().decrypt(token.encode()).decode()
