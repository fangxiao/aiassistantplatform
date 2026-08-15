"""平台规范与模版分发 API (供远程插件 CLI 同步最新规范与协议)。"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/specs", tags=["specs"])


class SpecsResponse(BaseModel):
    version: str
    template_agents_md: str


@router.get("/agents-md", response_model=SpecsResponse)
async def get_latest_specs() -> SpecsResponse:
    """获取平台最新版本的 AGENTS.md / CLAUDE.md 规范模版。"""
    from agentplatform.cli.main import TEMPLATE_AGENTS_MD

    return SpecsResponse(
        version="0.1.0",
        template_agents_md=TEMPLATE_AGENTS_MD,
    )
