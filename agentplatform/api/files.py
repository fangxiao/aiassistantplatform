"""文件预览与下载接口 (支持 HTML 实时在线预览与附件下载)。

安全边界(2026-09-17 收敛;2026-09-26 增加签名 URL):
- 默认需要登录(get_current_user);
- 路径白名单:仅允许访问 cwd、~/.agentplatform 及 settings.file_serve_roots
  配置的额外根目录内的文件——修复此前任意绝对路径可读的越权问题;
- **签名豁免**:携带有效 sig/exp(HMAC-SHA256,密钥=SECRET_KEY)的 URL 免头访问。
  动机:HTML 产物里的 <img>、新标签页 <a> 等上下文无法携带 Bearer 头,
  无签名则此类图片/链接必然 401(用户实测文章配图全裂)。签名与路径绑定
  且带过期时间,等效 S3 presigned URL 的安全性。
"""

import hashlib
import hmac
import mimetypes
import time
from pathlib import Path
from urllib.parse import unquote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from agentplatform.config import settings
from agentplatform.core.auth.dependencies import get_current_user, get_optional_current_user
from agentplatform.core.auth.model import User

router = APIRouter(prefix="/files", tags=["files"])

# 签名 URL 有效期:预览文章/配图的典型消费窗口(7 天)
FILE_URL_SIG_TTL = 7 * 24 * 3600


def sign_file_path(path: str, ttl: int = FILE_URL_SIG_TTL) -> str:
    """为文件路径生成带签名的 /api/files/raw 相对 URL(免 Bearer 访问)。"""
    exp = str(int(time.time()) + ttl)
    sig = _file_sig(path, exp)
    return f"/api/files/raw?{urlencode({'path': path, 'exp': exp, 'sig': sig})}"


def _file_sig(path: str, exp: str) -> str:
    msg = f"{path}:{exp}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()


def _sig_valid(path: str, exp: str | None, sig: str | None) -> bool:
    if not exp or not sig:
        return False
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(_file_sig(path, exp), sig)


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
    exp: str | None = Query(None, description="签名过期时间戳(与 sig 配对使用)"),
    sig: str | None = Query(None, description="HMAC-SHA256 路径签名"),
    user: User | None = Depends(get_optional_current_user),
):
    """在线直接预览文件 (如 HTML 网页直接在浏览器渲染展示)。

    鉴权:有效签名(sig/exp)免头访问;否则需登录——<img>/<a> 等上下文
    无法携带 Bearer,签名是此类场景唯一可行通道。
    """
    if not _sig_valid(path, exp, sig) and user is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "缺少认证令牌"}
        )
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
    exp: str | None = Query(None, description="签名过期时间戳(与 sig 配对使用)"),
    sig: str | None = Query(None, description="HMAC-SHA256 路径签名"),
    user: User | None = Depends(get_optional_current_user),
):
    """下载文件附件(鉴权规则同 /raw:签名或登录)。"""
    if not _sig_valid(path, exp, sig) and user is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "缺少认证令牌"}
        )
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

    # 签名 URL:<img> 无法携带 Bearer;public_api_base 配置时返回绝对地址
    signed = sign_file_path(str(target))
    if settings.public_api_base:
        signed = settings.public_api_base.rstrip("/") + signed
    return {"url": signed, "size": len(data)}
