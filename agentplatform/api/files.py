"""文件预览与下载接口 (支持 HTML 实时在线预览与附件下载)。

安全边界(2026-09-17 收敛):
- 需要登录(get_current_user);
- 路径白名单:仅允许访问 cwd、~/.agentplatform 及 settings.file_serve_roots
  配置的额外根目录内的文件——修复此前任意绝对路径可读的越权问题。
"""

import mimetypes
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from agentplatform.config import settings
from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User

router = APIRouter(prefix="/files", tags=["files"])


def _allowed_roots() -> list[Path]:
    """可访问的根目录(解析符号链接后匹配)。"""
    candidates = [
        Path.cwd(),
        Path.home() / ".agentplatform",
        *(Path(p).expanduser() for p in settings.file_serve_roots),
    ]
    return [c.resolve() for c in candidates if c.exists()]


def _within_roots(p: Path, roots: list[Path]) -> bool:
    return any(p == root or root in p.parents for root in roots)


def _resolve_file_path(raw_path: str) -> Path:
    """解析并校验文件路径:相对路径在白名单根下查找;绝对路径须落在白名单内。"""
    decoded = unquote(raw_path).strip()
    if decoded.startswith("file://"):
        decoded = decoded[7:]
    if not decoded:
        raise HTTPException(status_code=422, detail="路径为空")

    roots = _allowed_roots()
    p = Path(decoded)

    if p.is_absolute():
        p = p.resolve()
    else:
        # 相对路径:在白名单根下找第一个命中的文件(保持旧版候选目录语义)
        found = next(
            (c.resolve() for c in (root / decoded for root in roots) if c.exists() and c.is_file()),
            None,
        )
        if found is None:
            raise HTTPException(status_code=404, detail=f"文件不存在: {raw_path}")
        p = found

    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {raw_path}")
    if not _within_roots(p, roots):
        # 越权路径不泄露白名单细节
        raise HTTPException(status_code=404, detail=f"文件不存在: {raw_path}")

    return p


@router.get("/raw")
async def get_raw_file(
    path: str = Query(..., description="文件路径(限白名单根目录内)"),
    user: User = Depends(get_current_user),
):
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
async def download_file(
    path: str = Query(..., description="文件路径(限白名单根目录内)"),
    user: User = Depends(get_current_user),
):
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


@router.post("/upload")
async def upload_image(
    file: UploadFile,
    user: User = Depends(get_current_user),
) -> dict:
    """打磨④:对话图片上传——对象存储化(dataURL 不再直存消息表)。

    存 ~/.agentplatform/uploads/,返回白名单内可预览的 /api/files/raw URL。
    """
    # 打磨⑥:单文档即问——除图片外允许 pdf/md/txt(对话级临时解析,不入知识库)
    allowed = file.content_type and (
        file.content_type.startswith("image/")
        or file.content_type in ("application/pdf", "text/markdown", "text/plain")
        or (file.filename or "").lower().endswith((".pdf", ".md", ".markdown", ".txt"))
    )
    if not allowed:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "仅支持图片或 PDF/Markdown/文本"},
        )
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail={"code": "validation_error", "message": "文件不能超过 5MB"})

    import uuid as _uuid

    from agentplatform.core.db.engine import SessionLocal  # noqa: F401  保持 DB 依赖标注一致

    uploads = Path.home() / ".agentplatform" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "img.png").suffix.lower() or ".png"
    target = uploads / f"{_uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)

    url = f"/api/files/raw?path={target}"
    return {"url": url, "size": len(data)}
