"""插件数据存储原语(平台域无关能力,M34)。

平台只提供"按插件/用户/集合隔离的文档存储"这一通用机制——隔离、配额、
备份是平台职责;集合内的字段结构、查询语义由各插件自行定义(分层红线见
plugins/README.md)。插件工具经 ctx 拿到 user_id 后调用本服务,数据落
plugin_data 表(jsonb)。

过滤/排序均在 data->>field 的文本层做(ISO 日期字符串的字典序即时间序),
单用户量级足够;更复杂的查询是插件自己该在文档结构里规避的事。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as _delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.storage.model import PluginData

# 允许的过滤算子(文本比较)
_OPS = {"eq", "ne", "gt", "gte", "lt", "lte"}


def _text_col(field: str):
    """data->>field 的文本列。"""
    return PluginData.data[field].as_string()


def _apply_filters(stmt, filters: list[tuple[str, str, object]] | None):
    for field, op, value in filters or []:
        if op not in _OPS:
            raise ValueError(f"不支持的过滤算子: {op}")
        col = _text_col(field)
        v = str(value)
        stmt = {
            "eq": stmt.where(col == v),
            "ne": stmt.where(col != v),
            "gt": stmt.where(col > v),
            "gte": stmt.where(col >= v),
            "lt": stmt.where(col < v),
            "lte": stmt.where(col <= v),
        }[op]
    return stmt


async def put_doc(
    db: AsyncSession,
    *,
    plugin: str,
    user_id: str,
    collection: str,
    doc_id: str | None = None,
    data: dict,
) -> dict:
    """写入/覆盖一个文档(覆盖语义:同 doc_id 原地更新,created_at 保留)。"""
    doc_id = doc_id or uuid.uuid4().hex
    now = datetime.now(UTC)
    existing = await db.scalar(
        select(PluginData).where(
            PluginData.plugin_name == plugin,
            PluginData.user_id == str(user_id),
            PluginData.collection == collection,
            PluginData.doc_id == doc_id,
        )
    )
    if existing is not None:
        existing.data = data
        existing.updated_at = now
        await db.flush()
        return {"doc_id": doc_id, "created": False}
    db.add(
        PluginData(
            plugin_name=plugin,
            user_id=str(user_id),
            collection=collection,
            doc_id=doc_id,
            data=data,
            created_at=now,
            updated_at=now,
        )
    )
    await db.flush()
    return {"doc_id": doc_id, "created": True}


async def get_doc(
    db: AsyncSession, *, plugin: str, user_id: str, collection: str, doc_id: str
) -> dict | None:
    row = await db.scalar(
        select(PluginData).where(
            PluginData.plugin_name == plugin,
            PluginData.user_id == str(user_id),
            PluginData.collection == collection,
            PluginData.doc_id == doc_id,
        )
    )
    return dict(row.data) if row is not None else None


async def list_docs(
    db: AsyncSession,
    *,
    plugin: str,
    user_id: str,
    collection: str,
    filters: list[tuple[str, str, object]] | None = None,
    order_by: str | None = None,
    desc: bool = True,
    limit: int = 100,
) -> list[dict]:
    """按过滤条件列文档;order_by 作用于 data->>field 文本比较。"""
    stmt = select(PluginData).where(
        PluginData.plugin_name == plugin,
        PluginData.user_id == str(user_id),
        PluginData.collection == collection,
    )
    stmt = _apply_filters(stmt, filters)
    if order_by:
        col = _text_col(order_by)
        stmt = stmt.order_by(col.desc() if desc else col.asc())
    else:
        stmt = stmt.order_by(PluginData.created_at.desc())
    rows = (await db.scalars(stmt.limit(max(1, min(limit, 500))))).all()
    return [dict(r.data) | {"doc_id": r.doc_id} for r in rows]


async def count_docs(
    db: AsyncSession,
    *,
    plugin: str,
    user_id: str,
    collection: str,
    filters: list[tuple[str, str, object]] | None = None,
) -> int:
    stmt = select(func.count()).select_from(PluginData).where(
        PluginData.plugin_name == plugin,
        PluginData.user_id == str(user_id),
        PluginData.collection == collection,
    )
    stmt = _apply_filters(stmt, filters)
    return int(await db.scalar(stmt) or 0)


async def delete_doc(
    db: AsyncSession, *, plugin: str, user_id: str, collection: str, doc_id: str
) -> bool:
    res = await db.execute(
        _delete(PluginData).where(
            PluginData.plugin_name == plugin,
            PluginData.user_id == str(user_id),
            PluginData.collection == collection,
            PluginData.doc_id == doc_id,
        )
    )
    return (res.rowcount or 0) > 0
