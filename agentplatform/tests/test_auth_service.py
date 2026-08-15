"""认证服务单测(不依赖 PG):密码哈希 + JWT 签发/校验。"""

import pytest

from agentplatform.core.auth.errors import AuthError
from agentplatform.core.auth.service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHash:
    def test_hash_and_verify(self) -> None:
        h = hash_password("secret-pass")
        assert h != "secret-pass"
        assert verify_password("secret-pass", h)

    def test_verify_wrong(self) -> None:
        h = hash_password("correct")
        assert not verify_password("wrong", h)

    def test_salt_means_distinct_hashes(self) -> None:
        assert hash_password("same") != hash_password("same")


class TestJwt:
    def test_roundtrip(self) -> None:
        token = create_access_token("user-id-1", "developer")
        claims = decode_access_token(token)
        assert claims["sub"] == "user-id-1"
        assert claims["role"] == "developer"

    def test_invalid_token_raises(self) -> None:
        with pytest.raises(AuthError):
            decode_access_token("not-a-jwt")

    def test_tampered_token_raises(self) -> None:
        token = create_access_token("user-id-1", "user")
        tampered = token[:-2] + ("xx" if token[-2:] != "xx" else "yy")
        with pytest.raises(AuthError):
            decode_access_token(tampered)