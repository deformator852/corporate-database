"""Re-chunking: after CHUNK_SIZE or CHUNK_OVERLAP change (`uv run configure`),
documents processed before keep their chunks until an admin re-chunks them
from the System page. Optional: old and new chunk sizes search side by side.

Started here, run by the worker one document at a time
(`tasks.document.rechunk_next`) from the text saved at processing time; the
documents stay completed and searchable meanwhile. Progress shows in the
same banner as a model switch (`documents.reindexing`)."""

from typing import cast

from sqlalchemy import ColumnElement, CursorResult, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.document import Document, DocumentStatus
from services.search.index_model import save_reindex_total
from settings import chunk_overlap, chunk_size


def _outdated() -> list[ColumnElement[bool]]:
    """Completed documents cut with other settings than the current ones."""
    return [
        Document.status == DocumentStatus.COMPLETED,
        or_(
            Document.chunk_size.is_distinct_from(chunk_size()),
            Document.chunk_overlap.is_distinct_from(chunk_overlap()),
        ),
    ]


async def outdated_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Document).where(*_outdated())) or 0


async def mark_outdated(session: AsyncSession) -> int:
    """Marks the outdated documents for the worker; returns how many."""
    busy = await session.scalar(select(func.count()).select_from(Document).where(Document.reindexing.is_(True)))
    if busy:
        raise AppError("conflict", "The search index is already being rebuilt.", status_code=409)
    result = await session.execute(update(Document).where(*_outdated()).values(reindexing=True))
    # An UPDATE gives a CursorResult; the async API types it as Result.
    marked = cast(CursorResult, result).rowcount or 0
    await save_reindex_total(session, marked)
    return marked
