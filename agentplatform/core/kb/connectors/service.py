"""连接器同步编排(设计 009 §4,需求 U2/U8/U11)。

源 CRUD、触发同步(后台任务)、run 生命周期、幂等 upsert(新增/更新/跳过)、
全量型删除 diff→软删。同步入口统一走 trigger_sync(API 与调度器共用),
同 source 已有 running run 时拒绝,天然防重入与多 worker 重复触发。
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.kb.connectors.base import ADAPTERS, FetchedDoc, FetchResult
from agentplatform.core.kb.model import (
    KbChunk,
    KbDataSource,
    KbDataSourceType,
    KbDocument,
    KbDocumentStatus,
    KbSyncRun,
    KbSyncStatus,
)
from agentplatform.core.kb.pipeline import enqueue_document
from agentplatform.core.kb.service import KbError, kb_storage_dir

logger = logging.getLogger(__name__)


def decrypt_credentials(source: KbDataSource) -> dict:
    """解密数据源凭据;web 等无凭据类型返回空 dict。"""
    if not source.credentials_enc:
        return {}
    from agentplatform.core.llm import crypto

    return json.loads(crypto.decrypt(source.credentials_enc))


def validate_config(source_type: str, config: dict) -> dict:
    """建源/改源时的最小配置校验(与 adapter 类型相关的硬性字段)。"""
    if source_type not in ADAPTERS:
        raise KbError(f"不支持的数据源类型: {source_type!r}(可用: {sorted(ADAPTERS)})")
    if source_type == KbDataSourceType.web.value:
        urls = [u for u in (config.get("urls") or []) if str(u).strip()]
        if not urls:
            raise KbError("网页数据源至少配置一个种子 URL(config.urls)")
    return config


# ---------------------------------------------------------------- 源 CRUD


async def create_source(
    db: AsyncSession,
    kb_id: uuid.UUID,
    *,
    source_type: str,
    name: str,
    config: dict,
    credentials: dict | None = None,
    poll_interval_minutes: int | None = None,
) -> KbDataSource:
    """新建数据源(can_manage 鉴权在 API 层;配置在此校验)。"""
    validate_config(source_type, config)
    source = KbDataSource(
        kb_id=kb_id,
        type=KbDataSourceType(source_type),
        name=name.strip() or source_type,
        config=config,
        credentials_enc=_encrypt_credentials(credentials),
        poll_interval_minutes=poll_interval_minutes,
    )
    db.add(source)
    await db.flush()
    return source


def _encrypt_credentials(credentials: dict | None) -> str | None:
    if not credentials:
        return None
    from agentplatform.core.llm import crypto

    return crypto.encrypt(json.dumps(credentials))


async def get_source(
    db: AsyncSession, kb_id: uuid.UUID, source_id: uuid.UUID
) -> KbDataSource | None:
    source = await db.get(KbDataSource, source_id)
    if source is None or source.kb_id != kb_id:
        return None
    return source


async def list_sources(db: AsyncSession, kb_id: uuid.UUID) -> list[KbDataSource]:
    rows = await db.scalars(
        select(KbDataSource)
        .where(KbDataSource.kb_id == kb_id)
        .order_by(KbDataSource.created_at)
    )
    return list(rows)


# ---------------------------------------------------------------- 同步编排


async def trigger_sync(db: AsyncSession, source: KbDataSource) -> KbSyncRun:
    """创建 running run 并后台执行;同 source 已有 running run 时拒绝(防重入)。"""
    running = await db.scalar(
        select(func.count()).select_from(KbSyncRun).where(
            KbSyncRun.data_source_id == source.id,
            KbSyncRun.status == KbSyncStatus.running,
        )
    )
    if running:
        raise KbError("该数据源正在同步中,请稍候")
    run = KbSyncRun(data_source_id=source.id, status=KbSyncStatus.running)
    source.last_status = KbSyncStatus.running
    source.last_error = None
    db.add(run)
    await db.flush()
    source_id, run_id = source.id, run.id
    task = asyncio.create_task(_run_sync(source_id, run_id))
    task.add_done_callback(_log_task_exception)
    return run


def _log_task_exception(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("connector: 同步任务异常 %s", task.exception())


async def _run_sync(source_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """后台执行体:独立 Session,fetch → 幂等入库 → 删除 diff → 汇总。"""
    from agentplatform.core.db.engine import SessionLocal

    async with SessionLocal() as db:
        source = await db.get(KbDataSource, source_id)
        run = await db.get(KbSyncRun, run_id)
        if source is None or run is None:  # 源已被删除等竞态
            return
        try:
            adapter = ADAPTERS.get(source.type.value)
            if adapter is None:
                raise KbError(f"数据源类型无 adapter: {source.type.value}")
            result: FetchResult = await adapter(
                dict(source.config), decrypt_credentials(source)
            )
            stats = await _apply_result(db, source, result)
            for key, value in stats.items():
                setattr(run, key, value)
            run.status = (
                KbSyncStatus.failed if stats["failed_docs"] and not stats["added"] and not stats["updated"]
                else KbSyncStatus.partial if stats["failed_docs"]
                else KbSyncStatus.success
            )
            source.last_status = run.status
        except Exception as exc:  # noqa: BLE001  任何异常都落终态(验收 5/8)
            await db.rollback()
            run = await db.get(KbSyncRun, run_id)
            source = await db.get(KbDataSource, source_id)
            assert run is not None and source is not None
            run.status = KbSyncStatus.failed
            run.error = str(exc)[:500]
            source.last_status = KbSyncStatus.failed
            source.last_error = str(exc)[:500]
        finally:
            run.finished_at = datetime.now(UTC)
            source.last_sync_at = run.finished_at
            if source.last_status != KbSyncStatus.failed:
                source.last_error = None
            await db.commit()


async def _apply_result(
    db: AsyncSession, source: KbDataSource, result: FetchResult
) -> dict[str, int]:
    """幂等入库:新增/更新/跳过;full 型做删除 diff。返回计数 dict。"""
    from agentplatform.core.kb.model import KnowledgeBase

    kb = await db.get(KnowledgeBase, source.kb_id)
    if kb is None:
        raise KbError("所属知识库不存在")

    stats = {"added": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed_docs": 0}
    fetched_ids: set[str] = set()
    for doc in result.docs:
        fetched_ids.add(doc.external_id)
        try:
            action = await _upsert_document(db, kb, source, doc)
            stats[action] += 1
        except Exception as exc:  # noqa: BLE001  单文档失败不中断(验收 8)
            logger.warning("connector: 文档入库失败 %s: %s", doc.external_id, exc)
            stats["failed_docs"] += 1

    if result.full:
        stats["deleted"] += await _apply_deletions(db, source, fetched_ids)
    return stats


async def _upsert_document(
    db: AsyncSession, kb, source: KbDataSource, doc: FetchedDoc
) -> str:
    """单个外部文档幂等入库,返回 added/updated/skipped/failed_docs 之一。"""
    content = doc.content_markdown.encode("utf-8")
    if len(content) > settings.kb_max_document_mb * 1024 * 1024:
        logger.warning("connector: 文档超过单文档上限,跳过 %s", doc.external_id)
        return "failed_docs"
    content_hash = hashlib.sha256(content).hexdigest()

    existing = await db.scalar(
        select(KbDocument).where(
            KbDocument.data_source_id == source.id,
            KbDocument.external_id == doc.external_id,
            KbDocument.status != KbDocumentStatus.deleted,
        )
    )

    if existing is not None and existing.content_hash == content_hash:
        return "skipped"  # 未变更:不重复切分/向量化

    if existing is not None:  # 内容变更:覆写原文件重新走 pipeline(更新 chunk)
        path = kb_storage_dir(kb.id, existing.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        kb.size_bytes = max(0, (kb.size_bytes or 0) - existing.size_bytes) + len(content)
        existing.size_bytes = len(content)
        existing.content_hash = content_hash
        existing.status = KbDocumentStatus.pending
        existing.error = None
        enqueue_document(existing.id)
        return "updated"

    # 新文档:配额与库内 hash 去重(与手动上传同规则,验收 7)
    doc_count = await db.scalar(
        select(func.count()).select_from(KbDocument).where(
            KbDocument.kb_id == kb.id, KbDocument.status != KbDocumentStatus.deleted
        )
    )
    if (doc_count or 0) >= settings.kb_max_documents_per_kb:
        logger.warning("connector: 达到单库文档上限,跳过 %s", doc.external_id)
        return "failed_docs"
    dup = await db.scalar(
        select(KbDocument).where(
            KbDocument.kb_id == kb.id,
            KbDocument.content_hash == content_hash,
            KbDocument.status != KbDocumentStatus.deleted,
        )
    )
    if dup is not None:  # 库里已有同内容文档(可能来自手动上传):跳过不重复
        return "skipped"

    row = KbDocument(
        kb_id=kb.id,
        filename=f"{_safe_filename(doc.title)}.md",
        mime="text/markdown",
        size_bytes=len(content),
        content_hash=content_hash,
        origin="connector",
        source_app=source.type.value,
        data_source_id=source.id,
        external_id=doc.external_id,
        external_url=doc.url,
    )
    db.add(row)
    await db.flush()
    path = kb_storage_dir(kb.id, row.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    kb.doc_count = (kb.doc_count or 0) + 1
    kb.size_bytes = (kb.size_bytes or 0) + len(content)
    enqueue_document(row.id)
    return "added"


def _safe_filename(title: str) -> str:
    import re

    cleaned = re.sub(r"[\\/:*?\"<>|\n\r]+", "_", title).strip("._ ")
    return cleaned[:100] or "未命名"


async def _apply_deletions(
    db: AsyncSession, source: KbDataSource, fetched_ids: set[str]
) -> int:
    """全量型 diff:外部已不存在的文档软删(检索即时不可见,需求 U8)。"""
    rows = await db.scalars(
        select(KbDocument).where(
            KbDocument.data_source_id == source.id,
            KbDocument.status != KbDocumentStatus.deleted,
        )
    )
    stale = [d for d in rows if d.external_id not in fetched_ids]
    for doc in stale:
        await db.execute(sa_delete(KbChunk).where(KbChunk.document_id == doc.id))
        doc.status = KbDocumentStatus.deleted
    if stale:
        from agentplatform.core.kb.model import KnowledgeBase

        kb = await db.get(KnowledgeBase, source.kb_id)
        assert kb is not None
        kb.doc_count = max(0, (kb.doc_count or 0) - len(stale))
        kb.size_bytes = max(0, (kb.size_bytes or 0) - sum(d.size_bytes for d in stale))
        kb.chunk_count = await db.scalar(
            select(func.count()).select_from(KbChunk).where(KbChunk.kb_id == kb.id)
        ) or 0
    return len(stale)


async def list_runs(
    db: AsyncSession, source_id: uuid.UUID, limit: int = 10
) -> list[KbSyncRun]:
    rows = await db.scalars(
        select(KbSyncRun)
        .where(KbSyncRun.data_source_id == source_id)
        .order_by(KbSyncRun.started_at.desc())
        .limit(limit)
    )
    return list(rows)
