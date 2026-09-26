"""E2E 冒烟测试配置:对真实运行栈(容器/真实网关/SSE)跑,默认跳过。

启动方式(平台服务已在 localhost:8000 运行):
    uv run pytest agentplatform/tests/e2e -m e2e -q

教训背景(2026-09-26 插件联调日):单元测试 mock 掉 LLM/文件系统/SSE,
全部 319 绿的同时部署态插件瘫痪——本套件补集成缝,断言真实行为。
"""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)

