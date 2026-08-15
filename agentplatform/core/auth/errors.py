"""认证领域错误(对齐 core/agent/errors.py 模式)。

API 层统一转成 {error: {code, message}} 信封(005 §1)。
"""


class AuthError(Exception):
    """认证/用户相关错误。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code