import asyncio
from pathlib import Path
from collections.abc import Awaitable, Callable

from chonkie import RecursiveChunker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, engine
from exceptions import AppError
from i18n import t
from models.document import DONE_STATUSES, Document, DocumentStatus
from models.document_text import DocumentText
from models.notification import Notification, NotificationType
from services.documents.events import DocumentEventPublisher
from services.embedding import EmbeddingModel
from services.notifications.notification import NotificationService
from services.notifications.events import NotificationEventPublisher
from services.documents.parser import DocumentParser
from services.rag import Rag
from services.storage import ObjectStorage
from services.documents.text_cleanup import basic_clean, repeated_lines
from settings import (
    chunk_overlap,
    chunk_size,
    text_cleanup_mode,
)

EMBED_BATCH_SIZE = 8
# Data, not prose: no line-dropping rules, which could only lose values there.
_STRUCTURED = frozenset({".csv", ".json", ".xml", ".xlsx"})


def _split_text(
    chunker: RecursiveChunker, text: str, overlap: int
) -> tuple[list[str], list[int]]:
    """Chunks and where each starts in `text`. The offsets let long-document
    excerpts join neighbouring chunks exactly (services/chat.py)."""
    pieces = [piece for piece in chunker.chunk(text) if piece.text.strip()]
    chunks: list[str] = []
    starts: list[int] = []
    for index, piece in enumerate(pieces):
        start = piece.start_index
        if index:
            start = max(0, piece.start_index - overlap)
        raw = text[start : piece.end_index]
        chunk = raw.strip()
        if chunk:
            chunks.append(chunk)
            starts.append(start + len(raw) - len(raw.lstrip()))
    return chunks, starts


class DocumentProcessor:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        parser: DocumentParser,
        chunker: RecursiveChunker,
        embedder: EmbeddingModel,
        rag: Rag,
        events: DocumentEventPublisher,
        notifications: NotificationService,
    ) -> None:
        self.session = session
        self.storage = storage
        self.parser = parser
        self.chunker = chunker
        self.embedder = embedder
        self.rag = rag
        self.events = events
        self.notifications = notifications

    async def run(self, document_id: int) -> None:
        document = await self._require(document_id)
        if document is None or document.status in DONE_STATUSES:
            return
        try:
            content = await asyncio.to_thread(self.storage.get, document.object_key)
            await self.rag.delete_document(document.id)
            await self._set(document, DocumentStatus.PARSING, 15)
            text = await asyncio.to_thread(self.parser.parse, content, document.filename)
            # Chat reads this (the original) instead of re-parsing per question.
            await self.session.merge(DocumentText(document_id=document.id, text=text))
            await self._set(document, DocumentStatus.CHUNKING, 25)
            mode = text_cleanup_mode()
            structured = Path(document.filename).suffix.lower() in _STRUCTURED
            # `chunks` go to the Qdrant payload as written: search results and
            # long-document excerpts must show the document, not a cleanup
            # that dropped a table value. Only `searchable` (embedded) is cleaned.
            chunks, starts = _split_text(self.chunker, text, chunk_overlap())
            if not chunks:
                raise AppError("invalid", "The document has no text.", status_code=400)
            searchable = chunks
            if mode != "off":
                repeated = repeated_lines(text)
                searchable = [
                    basic_clean(chunk, structured=structured, repeated=repeated) or chunk
                    for chunk in chunks
                ]
            await self._set(document, DocumentStatus.EMBEDDING, 30)
            vectors: list[list[float]] = []
            total = len(searchable)
            for start in range(0, total, EMBED_BATCH_SIZE):
                batch = searchable[start : start + EMBED_BATCH_SIZE]
                vectors.extend(
                    await asyncio.to_thread(self.embedder.embed_passages, batch)
                )
                done = min(start + EMBED_BATCH_SIZE, total)
                progress = 30 + int(65 * done / total)
                await self._set(document, DocumentStatus.EMBEDDING, progress)
            await self.rag.upsert_chunks(
                document_id=document.id,
                name=document.name,
                filename=document.filename,
                classification=document.classification,
                chunks=chunks,
                starts=starts,
                vectors=vectors,
            )
            document.error_message = None
            document.ready_unannounced = True
            await self._set(document, DocumentStatus.COMPLETED, 100)
            await self._announce_ready(document)
        except AppError as exc:
            if exc.code == "not_found":
                raise
            try:
                await self.rag.delete_document(document.id)
            except AppError:
                pass
            if exc.status_code >= 500:
                raise
            document.error_message = t(exc.message)
            await self._set(document, DocumentStatus.FAILED, document.progress)
            await self._notify(
                document,
                NotificationType.DOCUMENT_PROCESS_FAILED,
                t(exc.message),
            )
            await self._announce_ready(document)
        except Exception:
            try:
                await self.rag.delete_document(document.id)
            except AppError:
                pass
            raise

    async def fail(self, document_id: int, message: str) -> None:
        document = await self._require(document_id)
        if document is None or document.status == DocumentStatus.COMPLETED:
            return
        try:
            await self.rag.delete_document(document.id)
        except AppError:
            pass
        document.error_message = t(message)
        await self._set(document, DocumentStatus.FAILED, document.progress)
        await self._notify(
            document,
            NotificationType.DOCUMENT_PROCESS_FAILED,
            t(message),
        )
        await self._announce_ready(document)

    async def drop_incomplete(self, document_id: int) -> None:
        document = await self._require(document_id)
        if document is None or document.status in DONE_STATUSES:
            return
        try:
            await self.rag.delete_document(document.id)
        except AppError:
            pass
        try:
            await asyncio.to_thread(self.storage.delete, document.object_key)
        except AppError:
            pass
        notification = await self._create_notice(
            document,
            NotificationType.DOCUMENT_PROCESS_FAILED,
            t('Could not process "{name}".', name=document.name),
        )
        user_id = document.user_id
        await self.session.delete(document)
        await self.session.commit()
        await self._emit(notification)
        if user_id is not None:
            await self.notifications.announce_ready(user_id)

    async def _create_notice(
        self,
        document: Document,
        type: NotificationType,
        message: str,
    ) -> Notification | None:
        if document.user_id is None:
            return None
        return await self.notifications.create(document.user_id, type, message)

    async def _notify(
        self,
        document: Document,
        type: NotificationType,
        message: str,
    ) -> None:
        notification = await self._create_notice(document, type, message)
        if notification is None:
            return
        await self.session.commit()
        await self._emit(notification)

    async def _announce_ready(self, document: Document) -> None:
        if document.user_id is not None:
            await self.notifications.announce_ready(document.user_id)

    async def _emit(self, notification: Notification | None) -> None:
        if notification is None:
            return
        await self.notifications.emit(notification)

    async def _require(self, document_id: int) -> Document | None:
        return await self.session.scalar(
            select(Document).where(Document.id == document_id)
        )

    async def _set(self, document: Document, status: DocumentStatus, progress: int) -> None:
        document.status = status
        document.progress = progress
        await self.session.commit()
        await self.session.refresh(document)
        try:
            await self.events.publish(document)
        except Exception:
            pass


async def unfinished_document_ids() -> list[int]:
    """Documents not completed or failed. Nothing runs while the (single)
    worker starts, so these lost their job: a crash, a restart, a bug."""
    try:
        async with AsyncSessionLocal() as session:
            ids = await session.scalars(
                select(Document.id)
                .where(Document.status.not_in(DONE_STATUSES))
                .order_by(Document.id)
            )
            return list(ids)
    finally:
        await engine.dispose()


async def process_document_job(document_id: int) -> None:
    await _with_processor(lambda processor: processor.run(document_id))


async def fail_document_job(document_id: int, message: str) -> None:
    await _with_processor(lambda processor: processor.fail(document_id, message))


async def drop_incomplete_document_job(document_id: int) -> None:
    await _with_processor(lambda processor: processor.drop_incomplete(document_id))


async def _with_processor(
    action: Callable[[DocumentProcessor], Awaitable[None]],
) -> None:
    storage = ObjectStorage()
    parser = DocumentParser()
    # Sizes come from CHUNK_SIZE / CHUNK_OVERLAP, read when the worker starts.
    chunker = RecursiveChunker(tokenizer="character", chunk_size=chunk_size())
    embedder = EmbeddingModel()
    rag = Rag()
    events = DocumentEventPublisher()
    note_events = NotificationEventPublisher()
    try:
        async with AsyncSessionLocal() as session:
            processor = DocumentProcessor(
                session,
                storage,
                parser,
                chunker,
                embedder,
                rag,
                events,
                NotificationService(session, note_events),
            )
            await action(processor)
    finally:
        await rag.client.close()
        await events.close()
        await note_events.close()
        # Each Celery task runs its own event loop (asyncio.run); pooled
        # connections are bound to this one and break the next task.
        await engine.dispose()
