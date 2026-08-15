"""交互服务异常类型。"""


class InteractError(Exception):
    """交互异常基类。"""

    def __init__(self, message: str, code: str = "interact_error", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
