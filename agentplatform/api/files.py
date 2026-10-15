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
import uuid
from pathlib import Path
from urllib.parse import unquote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.db.session import get_session
from agentplatform.core.kb.model import KbVisibility, KnowledgeBase
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
        # 数据目录路径翻译(T18.16):本地 CLI(宿主机)产出的 /Users/<u>/.agentplatform/...
        # 在服务端(容器)按字面解析不存在——统一映射到本服务数据根;翻译后仍受白名单约束
        if not p.exists() and ".agentplatform" in p.parts:
            parts = p.parts
            idx = parts.index(".agentplatform")
            translated = Path.home() / ".agentplatform" / Path(*parts[idx + 1 :])
            if translated.exists():
                p = translated
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


@router.api_route("/img", methods=["GET", "HEAD"])
async def proxy_image(
    u: str = Query(..., description="外链图片 URL"),
    exp: str | None = Query(None, description="签名过期时间戳"),
    sig: str | None = Query(None, description="HMAC 签名"),
    user: User | None = Depends(get_optional_current_user),
):
    """外链图片代理缓存(优化项8):服务端抓取+落盘缓存,免头签名访问。

    鉴权:有效签名或登录; SSRF 防护:仅公网 http/https;仅图片内容,≤10MB。
    """
    if not (u.startswith("http://") or u.startswith("https://")):
        raise HTTPException(status_code=422, detail="URL 需为 http/https")
    if not _sig_valid(f"img:{u}", exp, sig) and user is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "缺少认证令牌"}
        )
    import httpx as _httpx

    from agentplatform.core.agent.img_proxy import fetch_and_cache

    try:
        cached = await fetch_and_cache(u)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except _httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"上游图片获取失败: HTTP {exc.response.status_code}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"图片获取失败: {type(exc).__name__}")
    media_type, _ = mimetypes.guess_type(cached.name)
    return FileResponse(cached, media_type=media_type or "image/png", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/sign")
async def sign_file_url(
    path: str = Query(..., description="白名单内的文件路径"),
    user: User = Depends(get_current_user),
) -> dict:
    """为白名单内文件生成带签名的免头访问 URL(登录用户专用)。"""
    target = _resolve_file_path(path)  # 复用白名单校验
    signed = sign_file_path(str(target))
    if settings.public_api_base:
        signed = settings.public_api_base.rstrip("/") + signed
    return {"url": signed}


@router.post("/upload")
async def upload_image(
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """打磨④:对话图片上传——对象存储化(dataURL 不再直存消息表)。

    存 ~/.agentplatform/uploads/,返回白名单内可预览的 /api/files/raw URL。
    """
    # 打磨⑥:单文档即问——除图片外允许 pdf/md/txt/docx/xlsx(对话级临时解析,不入知识库)
    allowed = file.content_type and (
        file.content_type.startswith("image/")
        or file.content_type
        in (
            "application/pdf",
            "text/markdown",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        or (file.filename or "").lower().endswith(
            (".pdf", ".md", ".markdown", ".txt", ".docx", ".xlsx")
        )
    )
    if not allowed:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "仅支持图片或 PDF/Word/Excel/Markdown/文本"},
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

    # 20261015「我的文件」:上传留痕,供面板列全量附件与一键转存知识库
    from agentplatform.core.files.model import UserFile

    db.add(
        UserFile(
            user_id=str(user.id),
            path=str(target),
            name=file.filename or target.name,
            size=len(data),
            mime=file.content_type or "application/octet-stream",
        )
    )
    await db.commit()

    return {"url": signed, "size": len(data)}


class FileOut(BaseModel):
    id: uuid.UUID
    name: str
    size: int
    mime: str
    url: str
    created_at: str


@router.get("/mine", response_model=list[FileOut])
async def my_files(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[FileOut]:
    """我的文件:当前用户上传过的全部附件(20261015「我的文件」面板数据源)。"""
    from sqlalchemy import select as _select

    from agentplatform.core.files.model import UserFile

    rows = (
        await session.scalars(
            _select(UserFile)
            .where(UserFile.user_id == str(user.id))
            .order_by(UserFile.created_at.desc())
            .limit(200)
        )
    ).all()
    out: list[FileOut] = []
    for r in rows:
        signed = sign_file_path(r.path)
        if settings.public_api_base:
            signed = settings.public_api_base.rstrip("/") + signed
        out.append(
            FileOut(
                id=r.id,
                name=r.name,
                size=r.size,
                mime=r.mime,
                url=signed,
                created_at=r.created_at.isoformat(),
            )
        )
    return out


class IngestIn(BaseModel):
    kb_id: uuid.UUID | None = None  # None → 建/复用「我的知识库」个人默认库


@router.post("/{file_id}/ingest")
async def ingest_to_kb(
    file_id: uuid.UUID,
    payload: IngestIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """把「我的文件」转存知识库:公共库(有写权限)或个人默认库(20261015)。

    直读服务端本地文件走 KB 摄取管道(parse→chunk→embed),不经二次上传。
    """
    from pathlib import Path as _Path

    from fastapi import HTTPException as _HTTPException

    from agentplatform.core.files.model import UserFile
    from agentplatform.core.kb import pipeline as kb_pipeline
    from agentplatform.core.kb import service as kb_service

    uf = await session.get(UserFile, file_id)
    if uf is None or uf.user_id != str(user.id):
        raise _HTTPException(status_code=404, detail={"code": "not_found", "message": "文件不存在"})

    if payload.kb_id is not None:
        kb = await kb_service.get_kb(session, payload.kb_id)
        if kb is None or not await kb_service.can_write(session, kb, user):
            raise _HTTPException(
                status_code=404, detail={"code": "not_found", "message": "知识库不存在或无写权限"}
            )
    else:
        # 个人默认库:取/建「我的知识库」(private, owner=当前用户, personal_default)
        kb = (
            await session.scalars(
                _select(KnowledgeBase).where(
                    KnowledgeBase.owner_id == str(user.id),
                    KnowledgeBase.personal_default.is_(True),
                )
            )
        ).first()
        if kb is None:
            kb = KnowledgeBase(
                name="我的知识库",
                slug=f"kb-mine-{uuid.uuid4().hex[:8]}",
                visibility=KbVisibility.private,
                owner_id=str(user.id),
                description="我的个人知识库(随对话自动挂载,可关闭)",
                personal_default=True,
            )
            session.add(kb)
            await session.flush()

    src = _Path(uf.path)
    if not src.exists():
        raise _HTTPException(
            status_code=410, detail={"code": "gone", "message": "文件已过期,请重新上传"}
        )
    # 文件名兜底:回填的历史记录可能缺扩展名(name='raw' 等)——依次回落
    # 存储路径后缀、mime 映射,保证 KB 类型校验(按扩展名)能通过
    filename = uf.name
    if "." not in filename:
        filename = src.name
    if "." not in filename:
        ext_by_mime = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "text/markdown": ".md",
            "text/plain": ".txt",
        }
        filename = f"{src.stem or 'file'}{ext_by_mime.get(uf.mime, '')}"
    try:
        doc = await kb_service.add_document(
            session, kb, user,
            filename=filename,
            mime=uf.mime,
            content=src.read_bytes(),
        )
    except kb_service.KbError as exc:
        raise _HTTPException(status_code=400, detail={"code": "kb_error", "message": str(exc)}) from exc
    await session.commit()
    kb_pipeline.enqueue_document(doc.id)
    return {
        "doc_id": str(doc.id),
        "kb_id": str(kb.id),
        "kb_name": kb.name,
        "personal_default": bool(kb.personal_default),
    }
