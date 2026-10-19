"""Which documents have no file in the configured storage: after STORAGE
changed without moving the files (`uv run configure`), or a file removed
from the storage by hand. The backend checks every document when it starts,
since the storage changes only with a restart; the Documents and System
pages show the result (`documents.file_missing`)."""

import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.document import Document
from services.storage import FileStore

logger = logging.getLogger(__name__)


async def mark_missing_files(session: AsyncSession, store: FileStore) -> int:
    """Sets `file_missing` of every document; returns how many miss it."""
    rows = (await session.execute(select(Document.id, Document.object_key, Document.file_missing))).all()
    missing = 0
    for document_id, key, flagged in rows:
        absent = not await asyncio.to_thread(store.exists, key)
        missing += absent
        if absent != flagged:
            await session.execute(update(Document).where(Document.id == document_id).values(file_missing=absent))
    await session.commit()
    if missing:
        logger.warning("%s document(s) have no file in the storage", missing)
    return missing
