"""健康检查接口。"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """存活探针(不依赖 DB;DB 连通性由迁移与集成测试验证)。"""
    return {"status": "ok"}
