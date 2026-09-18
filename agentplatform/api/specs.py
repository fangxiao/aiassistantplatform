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


@router.get("/capabilities")
async def get_capabilities() -> dict:
    """获取平台共享能力全景清单 (Skill / Tool / 22 种 ContentBlock 控件)。"""
    from agentplatform.core.registry.capabilities import get_capabilities_manifest

    return get_capabilities_manifest()


@router.get("/agents-md", response_model=SpecsResponse)
async def get_latest_specs() -> SpecsResponse:
    """获取平台最新版本的 AGENTS.md / CLAUDE.md 规范模版。"""
    from agentplatform.cli.main import TEMPLATE_AGENTS_MD

    return SpecsResponse(
        version="0.3.0",
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


INSTALL_SH_TEMPLATE = """\
#!/bin/sh
# AgentPlatform CLI 一键安装(curl -fsSL {target}/api/specs/install.sh | sh)
# uv tool 安装:全局 agentplatform 命令、隔离环境、升级即重跑本脚本。
set -e
TARGET="${{AGENTPLATFORM_TARGET:-{target}}}"
PKG="$TARGET/api/specs/package.tar.gz"

if command -v uv >/dev/null 2>&1; then
  # 清理代理变量,防止全局代理拦截对局域网平台的访问
  exec env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy \\
       -u HTTPS_PROXY -u https_proxy uv tool install --force "$PKG"
fi

echo "未找到 uv;请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
echo "或使用 pipx: pipx install \\"$PKG\\"" >&2
exit 1
"""


@router.get("/install.sh")
async def install_script() -> Response:
    """一键安装脚本:uv tool install 平台代码包,体验对齐 npx(一条命令,全局命令可用)。"""
    from agentplatform.config import settings

    target = str(settings.public_base_url).rstrip("/") if getattr(settings, "public_base_url", None) else "http://localhost:8000"
    return Response(
        content=INSTALL_SH_TEMPLATE.format(target=target),
        media_type="text/x-shellscript",
        headers={"Content-Disposition": "inline; filename=install.sh"},
    )



@router.get("/templates")
async def list_templates() -> list[dict]:
    """插件模板清单(M16):id/name/description;init --template 消费。"""
    from agentplatform.cli_templates import TEMPLATES

    return [
        {"id": tid, "name": t["name"], "description": t["description"]}
        for tid, t in TEMPLATES.items()
    ]


@router.get("/templates/{template_id}")
async def get_template(template_id: str) -> dict:
    """模板完整文件集;CLI init --template 拉取后按 {plugin_name} 占位符实例化。"""
    from agentplatform.cli_templates import TEMPLATES

    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")
    return tpl
