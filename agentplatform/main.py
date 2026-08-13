"""agentplatform 后端入口。

错误统一为 {error: {code, message}}(005 §1):HTTPException 与参数校验错误
经异常处理器包装后返回。业务路由由各里程碑挂载(见 001 §2.1、005)。
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agentplatform.api import api_router

app = FastAPI(title="agentplatform", version="0.1.0")
app.include_router(api_router, prefix="/api")


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
