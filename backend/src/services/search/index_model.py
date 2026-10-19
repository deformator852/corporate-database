"""Which embedding model built the search index.

Vectors of two models cannot be compared, and models of the same size are
not told apart by the collection, so the model's EMBEDDING_MODEL key is kept
in `system_state`. When EMBEDDING_MODEL names another model the index is
outdated: chat search is off and the worker leaves documents queued until
every document is embedded again, by an admin on the System page
(`POST /system/reindex`) or `uv run switch-embedding-model`.
"""

from dataclasses import dataclass
from typing import cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.document import Document, DocumentStatus
from models.system_state import SystemState
from services.search.rag import COLLECTION_NAME, Rag
from settings import embedding_model_key

INDEX_MODEL = "embedding_model"
# Documents the last rebuild marked (a model switch or a re-chunk), for its
# progress.
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
    await _save(session, INDEX_MODEL, key)
    await save_reindex_total(session, queued)


async def save_reindex_total(session: AsyncSession, queued: int) -> None:
    """How many documents a rebuild marked, for its progress."""
    await _save(session, REINDEX_TOTAL, str(queued))


async def _save(session: AsyncSession, name: str, value: str) -> None:
    statement = insert(SystemState).values(name=name, value=value)
    await session.execute(statement.on_conflict_do_update(index_elements=[SystemState.name], set_={"value": value}))
    await session.commit()


async def reindex_progress(session: AsyncSession) -> ReindexProgress:
    """How far the worker is with the documents the last rebuild marked."""
    left = await session.scalar(select(func.count()).select_from(Document).where(Document.reindexing.is_(True))) or 0
    if not left:
        return ReindexProgress(active=False, percent=100)
    total = max(int(await _value(session, REINDEX_TOTAL) or 0), left)
    return ReindexProgress(active=True, percent=(total - left) * 100 // total)


async def _value(session: AsyncSession, name: str) -> str | None:
    return await session.scalar(select(SystemState.value).where(SystemState.name == name))


async def record_index_model(session: AsyncSession) -> None:
    """On the first start, records EMBEDDING_MODEL as the index's model: an
    existing index was built with the configured model, which could not be
    changed while documents existed."""
    await session.execute(
        insert(SystemState)
        .values(name=INDEX_MODEL, value=embedding_model_key())
        .on_conflict_do_nothing(index_elements=[SystemState.name])
    )
    await session.commit()


async def outdated_index_model(session: AsyncSession) -> str | None:
    """The index's model when EMBEDDING_MODEL names another one, else None."""
    stored = await stored_index_model(session)
    return stored if stored not in (None, embedding_model_key()) else None


async def require_current_index(session: AsyncSession) -> None:
    """Raises AppError while the index is built with another model: its
    vectors cannot be compared with the configured model's."""
    if await outdated_index_model(session) is not None:
        raise AppError(
            "unavailable",
            "Search is off: the embedding model was changed. "
            "An administrator must rebuild the search index on the System page.",
            status_code=503,
        )


async def rebuild_index(session: AsyncSession, model: str) -> int:
    """Rebuilds the index for `model`, the configured one in the processes
    that embed: drops it, queues every processed document again and records
    `model`. Returns how many documents were queued; the caller has them
    processed. Resumable: until `model` is recorded a rerun repeats every step."""
    rag = Rag()
    try:
        if await rag.client.collection_exists(COLLECTION_NAME):
            await rag.client.delete_collection(COLLECTION_NAME)
    finally:
        await rag.client.close()
    result = await session.execute(
        update(Document)
        .where(Document.status == DocumentStatus.COMPLETED)
        .values(status=DocumentStatus.QUEUED, progress=0, reindexing=True, ready_unannounced=False)
    )
    await session.commit()
    # An UPDATE gives a CursorResult; the async API types it as Result.
    queued = cast(CursorResult, result).rowcount or 0
    await save_index_model(session, model, queued=queued)
    return queued
