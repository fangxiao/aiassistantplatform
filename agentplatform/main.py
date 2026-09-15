"""agentplatform 后端入口。

错误统一为 {error: {code, message}}(005 §1):HTTPException 与参数校验错误
经异常处理器包装后返回。业务路由由各里程碑挂载(见 001 §2.1、005)。
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentplatform.api import api_router
from agentplatform.config import settings

logger = logging.getLogger(__name__)

REAPER_INTERVAL = 60  # TTL 清理任务检查间隔(秒)


async def _ttl_reaper() -> None:
    """后台清理过期调试会话(设计 007 §3.6)。"""
    from agentplatform.core.plugin.dev_session import dev_manager

    while True:
        try:
            cleaned = await dev_manager.reap_expired()
            if cleaned:
                logger.info("已清理 %d 个过期调试会话", cleaned)
        except Exception as exc:  # noqa: BLE001  后台任务异常不能中断循环
            logger.warning("调试会话清理任务异常: %s", exc)
        await asyncio.sleep(REAPER_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    reaper = asyncio.create_task(_ttl_reaper())
    # M12:内置资源幂等补种(含 tool:kb_search,web 链路注册表可用)+ 知识库 worker
    from agentplatform.core.db.engine import SessionLocal as _DbSession
    from agentplatform.core.kb import pipeline as kb_pipeline
    from agentplatform.core.registry.service import seed_builtin

    try:
        async with _DbSession() as db:
            await seed_builtin(db)
    except Exception as exc:  # noqa: BLE001  DB 未就绪不阻塞启动(迁移后重启即恢复)
        logger.warning("内置资源补种跳过: %s", exc)
    await kb_pipeline.start_worker()
    # M13:连接器轮询调度器(启动即扫一轮,重启恢复;设计 009 §6)
    from agentplatform.core.kb.connectors import scheduler as connector_scheduler

    connector_scheduler.start()
    # M15:定时任务(agent run)调度器(设计 011 §3)
    from agentplatform.core.scheduler import scheduler as task_scheduler

    task_scheduler.start()
    yield
    await task_scheduler.stop()
    await connector_scheduler.stop()
    await kb_pipeline.stop_worker()
    reaper.cancel()


app = FastAPI(title="agentplatform", version="0.1.0", lifespan=lifespan)
app.include_router(api_router, prefix="/api")

# 前端跨域(dev:localhost:3000;来源按 CORS_ORIGINS 环境变量覆盖)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException -> {error: {code, message}}。"""
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", "http_error")
        message = exc.detail.get("message", str(exc.detail))
    else:
        code, message = "http_error", str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """参数校验失败 -> 422 {error: {code, message}}。"""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "请求参数不合法",
                "details": exc.errors(),
            }
        },
    )
