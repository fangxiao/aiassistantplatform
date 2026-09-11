"""文档处理 pipeline(设计 008 §6,T12.5)。

状态机:pending → parsing → embedding → ready(任一步失败 → failed,可重试)。
MVP 单进程 asyncio.Queue 串行消费;启动时扫描非 ready 文档重新入队
(重启丢弃由文档状态驱动补偿,见 T12.5)。
"""

import asyncio
import logging
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.db.engine import SessionLocal
from agentplatform.core.kb.model import KbChunk, KbDocument, KbDocumentStatus, KnowledgeBase
from agentplatform.core.kb.service import kb_storage_dir
from agentplatform.core.llm.embeddings import (
    embed_texts,
    estimate_tokens,
    resolve_embedding_endpoint,
)

logger = logging.getLogger(__name__)

_queue_inst: asyncio.Queue[uuid.UUID] | None = None
_worker_task: asyncio.Task | None = None


def _queue() -> asyncio.Queue[uuid.UUID]:
    global _queue_inst
    if _queue_inst is None:
        _queue_inst = asyncio.Queue()
    return _queue_inst


def enqueue_document(doc_id: uuid.UUID) -> None:
    """入队一个待处理文档(应用进程内;API 层上传后调用)。"""
    _queue().put_nowait(doc_id)


async def start_worker() -> None:
    """启动常驻 worker;并补偿性重入队所有非终态文档(lifespan 调用)。"""
    global _worker_task
    await _requeue_stale()
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker())


async def stop_worker() -> None:
    """停止 worker(lifespan shutdown)。"""
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None


async def _requeue_stale() -> None:
    """启动补偿:把 pending/parsing/embedding 状态的文档重新入队。"""
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(KbDocument.id).where(
                KbDocument.status.in_(
                    [KbDocumentStatus.pending, KbDocumentStatus.parsing, KbDocumentStatus.embedding]
                )
            )
        )
        doc_ids = list(rows)
    for did in doc_ids:
        enqueue_document(did)
    if doc_ids:
        logger.info("补偿重入队 %d 个未完成文档", len(doc_ids))


async def _worker() -> None:
    """串行消费队列;单个文档失败不影响后续。"""
    while True:
        doc_id = await _queue().get()
        try:
            async with SessionLocal() as db:
                await process_document(db, doc_id)
                await db.commit()
        except Exception:  # noqa: BLE001,RUF100  pipeline 单文档异常不中断 worker
            logger.exception("文档处理失败: %s", doc_id)
        finally:
            _queue().task_done()


# ---------------------------------------------------------------- 解析与切分


def parse_document(mime: str, path: Path) -> str:
    """提取纯文本;pdf 走 pypdf(与 tool:pdf_parse 同源),md/txt 直读,html 去标签。"""
    if mime == "application/pdf":
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("pdf 解析需要 pypdf 依赖") from exc
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if mime in ("text/markdown", "text/plain"):
        return path.read_text(encoding="utf-8", errors="replace")
    if mime == "text/html":
        return _html_to_text(path.read_text(encoding="utf-8", errors="replace"))
    raise ValueError(f"不支持的 mime: {mime}")


# ---------------------------------------------------------------- html 去标签


class _TextExtractor(HTMLParser):
    """块级标签断行、忽略 script/style,提取纯文本(设计 008 §11.1)。"""

    _BLOCK_TAGS: ClassVar[set[str]] = {
        "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
        "section", "article", "header", "footer", "blockquote", "pre",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._pieces: list[str] = []
        self._skip_depth = 0  # script/style 嵌套深度

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._pieces.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self._pieces).splitlines()).strip()


def _html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.text()


def chunk_text(
    text: str,
    *,
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[tuple[int, int]]:
    """切分为 [(start_char, end_char)] 片段坐标(保留原文偏移供 source_span 溯源)。

    算法:按 \n\n 分段 → 顺序合并小段到目标 token → 单段超长按估算字符窗口硬切
    (带重叠)。token 为估算值(embeddings.estimate_tokens),MVP 精度足够。
    """
    target = target_tokens or settings.kb_chunk_tokens
    overlap = overlap_tokens or settings.kb_chunk_overlap_tokens

    # 1. 段落切分(保留字符偏移)
    paragraphs: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        idx = text.find("\n\n", start)
        end = idx if idx != -1 else len(text)
        if text[start:end].strip():
            paragraphs.append((start, end))
        if idx == -1:
            break
        start = idx + 2

    spans: list[tuple[int, int]] = []

    def hard_split(p_start: int, p_end: int) -> None:
        """超长段落硬切:按局部 chars/token 比率估算窗口,带重叠。"""
        seg_tokens = estimate_tokens(text[p_start:p_end])
        chars_per_token = max(1, (p_end - p_start) // max(1, seg_tokens))
        window = max(1, target * chars_per_token)
        step = max(1, window - overlap * chars_per_token)
        cursor = p_start
        while cursor < p_end:
            spans.append((cursor, min(p_end, cursor + window)))
            cursor += step

    # 2. 合并小段到目标 token
    buf_start: int | None = None
    buf_end = 0
    buf_tokens = 0
    for p_start, p_end in paragraphs:
        p_tokens = estimate_tokens(text[p_start:p_end])
        if p_tokens > target:
            if buf_start is not None:
                spans.append((buf_start, buf_end))
                buf_start, buf_tokens = None, 0
            hard_split(p_start, p_end)
            continue
        if buf_start is not None and buf_tokens + p_tokens > target:
            spans.append((buf_start, buf_end))
            buf_start, buf_tokens = None, 0
        if buf_start is None:
            buf_start, buf_tokens = p_start, 0
        buf_end = p_end
        buf_tokens += p_tokens
    if buf_start is not None:
        spans.append((buf_start, buf_end))
    return spans


# ---------------------------------------------------------------- 主流程


async def process_document(db: AsyncSession, doc_id: uuid.UUID) -> KbDocument:
    """处理单个文档:解析 → 切分 → 向量化 → 写片段 → ready。可重入(重试)。"""
    doc = await db.get(KbDocument, doc_id)
    if doc is None or doc.status in (KbDocumentStatus.ready, KbDocumentStatus.deleted):
        if doc is not None:
            return doc
        raise ValueError(f"文档不存在: {doc_id}")
    kb = await db.get(KnowledgeBase, doc.kb_id)
    if kb is None:
        raise ValueError(f"文档 {doc_id} 所属库不存在")

    try:
        # 1. parsing
        doc.status = KbDocumentStatus.parsing
        doc.error = None
        await db.commit()
        path = kb_storage_dir(doc.kb_id, doc.id)
        if not path.exists():
            raise FileNotFoundError(f"原始文件缺失: {path}")
        text = parse_document(doc.mime, path)
        if not text.strip():
            raise ValueError("解析结果为空文本(可能是扫描版 PDF)")

        # 2. chunking(保留原字符偏移用于 source_span 溯源)
        doc.status = KbDocumentStatus.embedding
        await db.commit()
        spans = chunk_text(text)
        if not spans:
            raise ValueError("切分结果为空")
        chunk_texts = [text[s:e] for s, e in spans]

        # 3. embedding + 写片段(重试时先清旧片段,幂等)
        from sqlalchemy import delete

        await db.execute(delete(KbChunk).where(KbChunk.document_id == doc.id))
        endpoint = await resolve_embedding_endpoint(db)
        vectors = await embed_texts(chunk_texts, endpoint)
        for i, (chunk, span) in enumerate(zip(chunk_texts, spans, strict=True)):
            db.add(
                KbChunk(
                    document_id=doc.id,
                    kb_id=doc.kb_id,
                    chunk_index=i,
                    text=chunk,
                    source_span={"start": span[0], "end": span[1]},
                    token_count=estimate_tokens(chunk),
                    embedding=vectors[i],
                )
            )

        doc.status = KbDocumentStatus.ready
        kb.chunk_count = len(chunk_texts)
        await db.commit()
        return doc
    except Exception as exc:  # noqa: BLE001  兜底:任何异常都必须落终态,文档不得滞留中间态
        await db.rollback()
        doc = await db.get(KbDocument, doc_id)
        assert doc is not None
        doc.status = KbDocumentStatus.failed
        doc.error = str(exc)[:500]
        await db.commit()
        return doc


async def retry_document(db: AsyncSession, doc: KbDocument) -> bool:
    """失败重试:重置为 pending 并入队。"""
    if doc.status != KbDocumentStatus.failed:
        return False
    doc.status = KbDocumentStatus.pending
    doc.error = None
    await db.commit()
    enqueue_document(doc.id)
    return True
