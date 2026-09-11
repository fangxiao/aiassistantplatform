"""httpx 客户端构建兜底(全局 SOCKS 代理环境适配)。

httpx 在客户端构造期就为 any://socks 代理创建传输层(与请求目标无关),
系统设置了 SOCKS 代理且未安装 socksio 时会直接 ImportError。
平台需直连本地/局域网服务(ollama、pgvector 侧车等),此时回退 trust_env=False。
"""

import httpx


def make_http_client(**kwargs: object) -> httpx.AsyncClient:
    """构建 httpx 客户端;SOCKS 环境缺 socksio 时回退直连。"""
    try:
        return httpx.AsyncClient(**kwargs)  # type: ignore[arg-type]
    except ImportError:
        return httpx.AsyncClient(**kwargs, trust_env=False)  # type: ignore[arg-type]
