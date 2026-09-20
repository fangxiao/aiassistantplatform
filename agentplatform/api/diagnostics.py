"""系统诊断 API(产品打磨①):一键连通性检查,部署排障 30 秒定位。

逐项探测并返回 {ok, detail};单项失败不影响其他项。匿名访问
(只暴露服务名与连通性,不泄露配置细节)。
"""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from agentplatform.config import settings

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class CheckResult(BaseModel):
    name: str
    ok: bool
    latency_ms: int | None = None
    detail: str


async def _probe_db() -> CheckResult:
    t0 = time.monotonic()
    try:
        from sqlalchemy import text

        from agentplatform.core.db.engine import SessionLocal

        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return CheckResult(name="database", ok=True, latency_ms=int((time.monotonic() - t0) * 1000), detail="PG 连接正常")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="database", ok=False, detail=f"PG 不可达: {type(exc).__name__}")


async def _probe_redis() -> CheckResult:
    t0 = time.monotonic()
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await r.ping()
        await r.aclose()
        return CheckResult(name="redis", ok=True, latency_ms=int((time.monotonic() - t0) * 1000), detail="Redis PONG")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="redis", ok=False, detail=f"Redis 不可达: {type(exc).__name__}")


async def _probe_llm() -> CheckResult:
    """主 LLM 端点:列模型(最轻调用);走 DB 端点或 .env 网关。"""
    t0 = time.monotonic()
    try:
        from agentplatform.core.chat.service import make_llm_client

        # 不真正发对话,构造成功即端点配置有效;再 HEAD /models 探活
        import httpx

        async with httpx.AsyncClient(timeout=8) as client:
            if settings.openai_base_url and settings.openai_api_key:
                resp = await client.get(
                    f"{settings.openai_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
            else:
                return CheckResult(name="llm", ok=False, detail="未配置 OPENAI_BASE_URL/OPENAI_API_KEY")
        if resp.status_code == 200:
            return CheckResult(name="llm", ok=True, latency_ms=int((time.monotonic() - t0) * 1000),
                               detail=f"网关可达({resp.status_code}),默认模型 {settings.default_model}")
        return CheckResult(name="llm", ok=False, detail=f"网关响应异常: HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="llm", ok=False, detail=f"LLM 网关不可达: {type(exc).__name__}")


async def _probe_embedding() -> CheckResult:
    t0 = time.monotonic()
    try:
        from agentplatform.core.llm.embeddings import resolve_embedding_endpoint

        from sqlalchemy import text

        from agentplatform.core.db.engine import SessionLocal

        async with SessionLocal() as db:
            ep = await resolve_embedding_endpoint(db)
        if ep is None:
            return CheckResult(name="embedding", ok=False,
                               detail="无 embedding 端点(管理台添加 embedding 类型端点,或设 KB_EMBEDDING_MODEL)")
        import httpx

        from agentplatform.core.llm import crypto
        from agentplatform.core.llm.http_client import make_http_client

        key = crypto.decrypt(ep.api_key_enc) if ep.api_key_enc else ""
        async with make_http_client(timeout=8) as client:
            resp = await client.get(
                f"{ep.base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"}
            )
        if resp.status_code == 200:
            return CheckResult(name="embedding", ok=True, latency_ms=int((time.monotonic() - t0) * 1000),
                               detail=f"端点「{ep.name}」模型 {ep.model} 可达")
        return CheckResult(name="embedding", ok=False, detail=f"端点「{ep.name}」响应异常: HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="embedding", ok=False, detail=f"embedding 不可用: {type(exc).__name__}")


async def _probe_search() -> CheckResult:
    t0 = time.monotonic()
    try:
        if settings.web_search_provider == "searxng":
            import httpx

            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(f"{settings.searxng_base_url.rstrip('/')}/healthz")
            if resp.status_code in (200, 404):  # searxng 无 /healthz 时 404 也算可达
                return CheckResult(name="search", ok=True, latency_ms=int((time.monotonic() - t0) * 1000),
                                   detail=f"SearXNG 可达({settings.searxng_base_url}),provider=searxng 免费无限")
            return CheckResult(name="search", ok=False, detail=f"SearXNG 响应异常: HTTP {resp.status_code}")
        if not settings.web_search_api_key:
            return CheckResult(name="search", ok=False,
                               detail="未配置(WEB_SEARCH_API_KEY 或切换 WEB_SEARCH_PROVIDER=searxng)")
        return CheckResult(name="search", ok=True, detail=f"provider=tavily,key 已配置")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="search", ok=False, detail=f"搜索服务不可达: {type(exc).__name__}")


async def _probe_scheduler() -> CheckResult:
    try:
        from agentplatform.core.scheduler.scheduler import _task

        running = _task is not None and not _task.done()
        return CheckResult(name="scheduler", ok=running,
                           detail="定时任务调度器运行中" if running else "调度器未启动(单副本部署应常驻)")
    except Exception:  # noqa: BLE001
        return CheckResult(name="scheduler", ok=False, detail="调度器状态未知")


@router.get("", response_model=list[CheckResult])
async def run_diagnostics() -> list[CheckResult]:
    """一键体检:DB/Redis/LLM/Embedding/搜索/调度器。"""
    return [
        await _probe_db(),
        await _probe_redis(),
        await _probe_llm(),
        await _probe_embedding(),
        await _probe_search(),
        await _probe_scheduler(),
    ]
