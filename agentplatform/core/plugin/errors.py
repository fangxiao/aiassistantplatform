"""插件处理异常。"""


class PluginError(Exception):
    """插件处理失败基类。"""

    code = "plugin_error"


class PluginValidationError(PluginError):
    """清单/结构校验失败。"""

    code = "plugin_invalid"


class DependencyError(PluginError):
    """depends_on 依赖不满足(注册表中缺失或版本不兼容)。"""

    code = "dependency_missing"

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"依赖不满足: {', '.join(missing)}")
