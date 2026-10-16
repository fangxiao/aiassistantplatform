"""插件存储原语测试(M34 + 20261016 工单 1623-68129f:in/not_in 算子)。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.storage import service as store

PLUGIN = "test-plugin"
COLL = "items"


@pytest.fixture
async def seeded(session: AsyncSession):
    rows = [
        ("a1", {"status": "active", "expires_at": "2027-01-01", "n": 1}),
        ("a2", {"status": "expiring_soon", "expires_at": "2026-11-01", "n": 2}),
        ("a3", {"status": "expired", "expires_at": "2026-10-01", "n": 3}),
    ]
    for doc_id, data in rows:
        await store.put_doc(session, plugin=PLUGIN, user_id="u1", collection=COLL, doc_id=doc_id, data=data)
    await session.commit()
    return rows


async def test_in_operator(session: AsyncSession, seeded):
    docs = await store.list_docs(
        session, plugin=PLUGIN, user_id="u1", collection=COLL,
        filters=[("status", "in", ["active", "expiring_soon"])],
    )
    assert sorted(d["doc_id"] for d in docs) == ["a1", "a2"]


async def test_not_in_operator(session: AsyncSession, seeded):
    docs = await store.list_docs(
        session, plugin=PLUGIN, user_id="u1", collection=COLL,
        filters=[("status", "not_in", ["expired"])],
    )
    assert sorted(d["doc_id"] for d in docs) == ["a1", "a2"]


async def test_in_rejects_empty_and_scalar(session: AsyncSession, seeded):
    for bad in ([], "active"):
        with pytest.raises(ValueError, match="序列"):
            await store.list_docs(
                session, plugin=PLUGIN, user_id="u1", collection=COLL,
                filters=[("status", "in", bad)],
            )


async def test_user_isolation(session: AsyncSession, seeded):
    docs = await store.list_docs(
        session, plugin=PLUGIN, user_id="u2", collection=COLL,
        filters=[("status", "in", ["active", "expiring_soon", "expired"])],
    )
    assert docs == []
