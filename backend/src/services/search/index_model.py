"""Which embedding model built the search index.

Vectors of two models cannot be compared, and models of the same size are
not told apart by the collection, so the model's EMBEDDING_MODEL key is kept
in `system_state`. The backend and the worker refuse to start when
EMBEDDING_MODEL names another model: changing it needs every document
embedded again (`uv run switch-embedding-model`, src/switch_embedding_model).
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.document import Document
from models.system_state import SystemState
from settings import embedding_model_key

INDEX_MODEL = "embedding_model"
# Documents the last switch queued, for its progress.
REINDEX_TOTAL = "reindex_total"


@dataclass(frozen=True, slots=True)
class ReindexProgress:
    active: bool
    # Share of the queued documents embedded again, 0-100.
    percent: int


async def stored_index_model(session: AsyncSession) -> str | None:
    return await _value(session, INDEX_MODEL)


async def save_index_model(session: AsyncSession, key: str, *, queued: int = 0) -> None:
    """Records `key` as the index's model, and how many documents it queued."""
    for name, value in ((INDEX_MODEL, key), (REINDEX_TOTAL, str(queued))):
        statement = insert(SystemState).values(name=name, value=value)
        await session.execute(statement.on_conflict_do_update(index_elements=[SystemState.name], set_={"value": value}))
    await session.commit()


async def reindex_progress(session: AsyncSession) -> ReindexProgress:
    """How far the worker is with the documents the last switch queued."""
    left = await session.scalar(select(func.count()).select_from(Document).where(Document.reindexing.is_(True))) or 0
    if not left:
        return ReindexProgress(active=False, percent=100)
    total = max(int(await _value(session, REINDEX_TOTAL) or 0), left)
    return ReindexProgress(active=True, percent=(total - left) * 100 // total)


async def _value(session: AsyncSession, name: str) -> str | None:
    return await session.scalar(select(SystemState.value).where(SystemState.name == name))


async def verify_index_model(session: AsyncSession) -> None:
    """Raises AppError unless EMBEDDING_MODEL is the model of the index. The
    first start records it: an existing index was built with the configured
    model, which could not be changed while documents existed."""
    configured = embedding_model_key()
    stored = await stored_index_model(session)
    if stored is None:
        await session.execute(
            insert(SystemState)
            .values(name=INDEX_MODEL, value=configured)
            .on_conflict_do_nothing(index_elements=[SystemState.name])
        )
        await session.commit()
        stored = await stored_index_model(session)
    if stored == configured:
        return
    raise AppError(
        "misconfigured",
        f"EMBEDDING_MODEL is {configured}, but the documents are indexed with {stored}. "
        f"Set EMBEDDING_MODEL back to {stored}, or switch the model: "
        f"cd backend && uv run switch-embedding-model {configured}",
        status_code=500,
    )
