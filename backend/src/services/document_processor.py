import asyncio
from collections.abc import Awaitable, Callable

from chonkie import RecursiveChunker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from exceptions import AppError
from models.document import Document, DocumentStatus
from models.notification import Notification, NotificationType
from services.document_events import DocumentEventPublisher
from services.embedding import EmbeddingModel
from services.notification import NotificationService
from services.notification_events import NotificationEventPublisher
from services.parser import DocumentParser
from services.rag import Rag
from services.storage import ObjectStorage

EMBED_BATCH_SIZE = 8
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
_DONE = {DocumentStatus.COMPLETED, DocumentStatus.FAILED}


def _split_text(chunker: RecursiveChunker, text: str) -> list[str]:
    pieces = [piece for piece in chunker.chunk(text) if piece.text.strip()]
    chunks: list[str] = []
    for index, piece in enumerate(pieces):
        start = piece.start_index
        if index:
            start = max(0, piece.start_index - CHUNK_OVERLAP)
        chunk = text[start : piece.end_index].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


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
        if document is None or document.status in _DONE:
            return
        try:
            content = await asyncio.to_thread(self.storage.get, document.object_key)
            await self.rag.delete_document(document.id)
            await self._set(document, DocumentStatus.PARSING, 15)
            text = await asyncio.to_thread(self.parser.parse, content, document.filename)
            await self._set(document, DocumentStatus.CHUNKING, 30)
            chunks = _split_text(self.chunker, text)
            if not chunks:
                raise AppError("invalid", "The document has no text.", status_code=400)
            await self._set(document, DocumentStatus.EMBEDDING, 35)
            vectors: list[list[float]] = []
            total = len(chunks)
            for start in range(0, total, EMBED_BATCH_SIZE):
                batch = chunks[start : start + EMBED_BATCH_SIZE]
                vectors.extend(
                    await asyncio.to_thread(self.embedder.embed_passages, batch)
                )
                done = min(start + EMBED_BATCH_SIZE, total)
                progress = 35 + int(60 * done / total)
                await self._set(document, DocumentStatus.EMBEDDING, progress)
            await self.rag.upsert_chunks(
                document_id=document.id,
                name=document.name,
                filename=document.filename,
                classification=document.classification,
                chunks=chunks,
                vectors=vectors,
            )
            document.error_message = None
            await self._set(document, DocumentStatus.COMPLETED, 100)
            await self._notify(
                document,
                NotificationType.DOCUMENT_COMPLETED,
                f'"{document.name}" is ready.',
            )
        except AppError as exc:
            if exc.code == "not_found":
                raise
            try:
                await self.rag.delete_document(document.id)
            except AppError:
                pass
            if exc.status_code >= 500:
                raise
            document.error_message = exc.message
            await self._set(document, DocumentStatus.FAILED, document.progress)
            await self._notify(
                document,
                NotificationType.DOCUMENT_PROCESS_FAILED,
                exc.message,
            )
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
        document.error_message = message
        await self._set(document, DocumentStatus.FAILED, document.progress)
        await self._notify(
            document,
            NotificationType.DOCUMENT_PROCESS_FAILED,
            message,
        )

    async def drop_incomplete(self, document_id: int) -> None:
        document = await self._require(document_id)
        if document is None or document.status in _DONE:
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
            f'Could not process "{document.name}".',
        )
        await self.session.delete(document)
        await self.session.commit()
        await self._emit(notification)

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
    chunker = RecursiveChunker(tokenizer="character", chunk_size=CHUNK_SIZE)
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
