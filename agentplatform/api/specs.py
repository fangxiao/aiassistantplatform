import io
import tarfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.db.session import get_session

router = APIRouter(prefix="/specs", tags=["specs"])


class SpecsResponse(BaseModel):
    version: str
    template_agents_md: str


@router.get("/capabilities")
async def get_capabilities(db: AsyncSession = Depends(get_session)) -> dict:
    """获取平台共享能力全景清单 (Skill / Tool + 22 种 ContentBlock 控件)。

    M26:注入 use_count 热度(web 注册表徽标 + CLI registry 表格同源);
    计数为聚合读,不涉敏感数据(端点开放供远程 CLI)。
    """
    from agentplatform.core.registry.capabilities import (
        get_capabilities_manifest,
        usage_by_id,
    )

    return get_capabilities_manifest(await usage_by_id(db))


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
        headers={
            "Content-Disposition": "attachment; filename=agentplatform.tar.gz",
            # CF 按扩展名缓存 .gz(max-age=14400)导致远程 update 拿到旧包
            # (20261003 实证同 URL 多体积变体)——origin 明示禁缓存
            "Cache-Control": "no-store",
            # 部署水位(T18.21):CLI 比对此值判断本地包是否落后,避免
            # "平台热更已生效但本地 CLI 未同步"被误判为缺陷未修(今日三次)
            "X-Agentplatform-Rev": _deployed_rev(),
        },
    )


def _deployed_rev() -> str:
    """当前部署水位:REVISION 文件(镜像构建/热更时写入)> 环境变量 > 'unknown'。"""
    import os

    rev_file = Path(__file__).resolve().parent.parent.parent / "REVISION"
    if rev_file.exists():
        return rev_file.read_text(encoding="utf-8").strip()[:12]
    return os.environ.get("AGENTPLATFORM_REV", "unknown")[:12]


@router.get("/revision")
async def deployed_revision() -> dict:
    """部署水位查询(轻量):CLI 启动时 HEAD 比对,不一致提示 agentplatform update。"""
    return {"rev": _deployed_rev()}


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
