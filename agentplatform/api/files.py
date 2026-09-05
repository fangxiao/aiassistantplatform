"""文件预览与下载接口 (支持 HTML 实时在线预览与附件下载)。"""

import mimetypes
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/files", tags=["files"])


def _resolve_file_path(raw_path: str) -> Path:
    """解析文件路径。"""
    decoded = unquote(raw_path).strip()
    if decoded.startswith("file://"):
        decoded = decoded[7:]

    p = Path(decoded).resolve()

    if not p.exists() or not p.is_file():
        candidates = [
            Path.cwd() / decoded,
            Path.home() / ".agentplatform" / "outputs" / decoded,
            Path.home() / ".agentplatform" / decoded,
            Path("/Users/admin/work/project") / decoded,
            Path("/Users/admin/work/project/plugins/writewx") / decoded,
            Path("/Users/admin/work/project/plugins/contract") / decoded,
        ]
        found = next((c.resolve() for c in candidates if c.exists() and c.is_file()), None)
        if found:
            p = found
        else:
            raise HTTPException(status_code=404, detail=f"文件不存在: {raw_path}")

    return p


@router.get("/raw")
async def get_raw_file(path: str = Query(..., description="文件本地绝对路径或工作区相对路径")):
    """在线直接预览文件 (如 HTML 网页直接在浏览器渲染展示)。"""
    target = _resolve_file_path(path)
    mime_type, _ = mimetypes.guess_type(target.name)
    if not mime_type:
        mime_type = "text/html; charset=utf-8" if target.suffix.lower() == ".html" else "application/octet-stream"

    return FileResponse(
        target,
        media_type=mime_type,
        headers={"Content-Disposition": "inline"},
    )


@router.get("/download")
async def download_file(path: str = Query(..., description="文件本地绝对路径或工作区相对路径")):
    """下载文件附件。"""
    target = _resolve_file_path(path)
    mime_type, _ = mimetypes.guess_type(target.name)
    if not mime_type:
        mime_type = "application/octet-stream"

    return FileResponse(
        target,
        media_type=mime_type,
        filename=target.name,
    )
