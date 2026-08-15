import io
import tarfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response
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


@router.get("/package.tar.gz")
async def download_package() -> Response:
    """直接将当前平台服务端的最新代码打包为 tar.gz 提供下载安装(支持本地/测试阶段零 GitHub 依赖拉取)。"""
    root = Path(__file__).resolve().parent.parent.parent
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in root.rglob("*"):
            if any(
                part.startswith(".")
                or part in ("__pycache__", "node_modules", "dist", "build", "web", "docs")
                for part in p.parts
            ):
                continue
            if p.is_file():
                rel = p.relative_to(root)
                tar.add(p, arcname=str(rel))
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=agentplatform.tar.gz"},
    )

