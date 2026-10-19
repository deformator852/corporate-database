import asyncio
import re
from collections.abc import Awaitable, Callable
from itertools import pairwise
from pathlib import Path

from chonkie import RecursiveChunker
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, engine
from exceptions import AppError
from i18n import t, use_language
from models.document import DONE_STATUSES, Document, DocumentStatus
from models.document_text import DocumentText
from models.notification import Notification, NotificationType
from models.user import User
from services.documents.boilerplate import shared_lines
from services.documents.embedding_text import STRUCTURED, embedding_texts
from services.documents.events import DocumentEventPublisher
from services.documents.parser import DocumentParser
from services.notifications.events import NotificationEventPublisher
from services.notifications.notification import NotificationService
from services.search.embedding import EmbeddingModel
from services.search.index_model import outdated_index_model
from services.search.rag import Rag
from services.storage import ObjectStorage
from settings import (
    chunk_overlap,
    chunk_size,
    text_cleanup_mode,
)

EMBED_BATCH_SIZE = 8


# A Markdown heading line; Word and ODT headings are parsed into these.
_HEADING = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)


def _split_text(chunker: RecursiveChunker, text: str, overlap: int) -> tuple[list[str], list[int]]:
    """Chunks and where each starts in `text`. The offsets let long-document
    excerpts join neighbouring chunks exactly (services/chat/chat.py).

    A chunk never runs from one section into the next: the text is cut at
    headings first, small neighbouring sections are kept together up to the
    chunk size, and only a longer section is split inside."""
    chunks: list[str] = []
    starts: list[int] = []
    for begin, end in _sections(text, chunker.chunk_size):
        part_chunks, part_starts = _split_span(chunker, text, overlap, begin, end)
        chunks += part_chunks
        starts += part_starts
    return chunks, starts


def _sections(text: str, size: int) -> list[tuple[int, int]]:
    cuts = [match.start() for match in _HEADING.finditer(text) if match.start() > 0]
    bounds = [0, *cuts, len(text)]
    groups: list[tuple[int, int]] = []
    for begin, end in pairwise(bounds):
        if groups and end - groups[-1][0] <= size:
            groups[-1] = (groups[-1][0], end)
        else:
            groups.append((begin, end))
    return groups


def _split_span(
    chunker: RecursiveChunker, text: str, overlap: int, begin: int, end: int
) -> tuple[list[str], list[int]]:
    """Chunks of text[begin:end], with starts in `text`; each chunk after
    the first repeats `overlap` characters before it."""
    pieces = [piece for piece in chunker.chunk(text[begin:end]) if piece.text.strip()]
    chunks: list[str] = []
    starts: list[int] = []
    for index, piece in enumerate(pieces):
        start = piece.start_index
        if index:
            start = max(0, piece.start_index - overlap)
        raw = text[begin + start : begin + piece.end_index]
        chunk = raw.strip()
        if chunk:
            chunks.append(chunk)
            starts.append(begin + start + len(raw) - len(raw.lstrip()))
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
        if await outdated_index_model(self.session) is not None:
            return  # stays queued: rebuilding the index queues it again
        try:
            text = await self._parse(document)
            await self._set(document, DocumentStatus.CHUNKING, 25)
            # `chunks` go to the Qdrant payload as written: search results and
            # long-document excerpts must show the document, not a cleanup
            # that dropped a table value. Only the embedded text is cleaned,
            # and table chunks get the header row (embedding_text.py).
            chunks, starts = _split_text(self.chunker, text, chunk_overlap())
            if not chunks:
                raise AppError("invalid", "The document has no text.", status_code=400)
            searchable = await self._searchable(document, text, chunks, starts)
            vectors = await self._embed(document, searchable)
            await self.rag.upsert_chunks(
                document_id=document.id,
                name=document.name,
                filename=document.filename,
                classification=document.classification,
                chunks=chunks,
                starts=starts,
                vectors=vectors,
                indexed=searchable,
            )
            document.error_message = None
            document.chunk_size, document.chunk_overlap = chunk_size(), chunk_overlap()
            document.ready_unannounced = not document.reindexing
            document.reindexing = False
            await self._set(document, DocumentStatus.COMPLETED, 100)
            await self._announce_ready(document)
        except AppError as exc:
            if exc.code == "not_found":
                raise
            await self._drop_index(document.id)
            if exc.status_code >= 500:
                raise
            document.error_message = t(exc.message, **exc.params)
            # No longer searchable: the owner hears of it, and of a later retry.
            document.reindexing = False
            await self._set(document, DocumentStatus.FAILED, document.progress)
            await self._notify(document, NotificationType.DOCUMENT_PROCESS_FAILED, t(exc.message, **exc.params))
            await self._announce_ready(document)
        except Exception:
            await self._drop_index(document.id)
            raise

    async def rechunk(self, document_id: int) -> None:
        """Cuts a completed document again with the current CHUNK_SIZE and
        CHUNK_OVERLAP, from its saved text. It stays completed and searchable
        meanwhile: the new chunks replace the old ones of the same number,
        then the ones past the new count go. A failure leaves the old
        chunks, and the document is offered for re-chunking again."""
        document = await self._require(document_id)
        if document is None or document.status != DocumentStatus.COMPLETED:
            return  # deleted, or queued again (a model switch) meanwhile
        if await outdated_index_model(self.session) is not None:
            return  # rebuilding the index embeds it again anyway
        saved = await self.session.get(DocumentText, document.id)
        if saved is None:
            return
        chunks, starts = _split_text(self.chunker, saved.text, chunk_overlap())
        if not chunks:
            return
        searchable = await self._searchable(document, saved.text, chunks, starts)
        # The lines just recorded hold a key lock on the document row: freed
        # here, or deleting it would wait for the whole embedding.
        await self.session.commit()
        vectors = await self._embed(document, searchable, report=False)
        # Locked until the commit: a rename, a new classification or a
        # delete made meanwhile waits, and the chunks carry the current
        # values. Without the lock they could bring back the old
        # classification, or outlive the deleted document.
        document = await self.session.scalar(
            select(Document)
            .where(Document.id == document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if document is None or document.status != DocumentStatus.COMPLETED:
            return
        await self.rag.upsert_chunks(
            document_id=document.id,
            name=document.name,
            filename=document.filename,
            classification=document.classification,
            chunks=chunks,
            starts=starts,
            vectors=vectors,
            indexed=searchable,
        )
        await self.rag.delete_chunks_from(document.id, len(chunks))
        document.chunk_size, document.chunk_overlap = chunk_size(), chunk_overlap()
        await self.session.commit()
        try:
            await self.events.publish(document)  # moves the rebuild's progress
        except Exception:
            pass

    async def _parse(self, document: Document) -> str:
        """The document's text, saved for the chat, which reads it instead of
        parsing the file again for every question."""
        content = await asyncio.to_thread(self.storage.get, document.object_key)
        await self.rag.delete_document(document.id)
        await self._set(document, DocumentStatus.PARSING, 15)
        text = await asyncio.to_thread(self.parser.parse, content, document.filename)
        await self.session.merge(DocumentText(document_id=document.id, text=text))
        return text

    async def _searchable(self, document: Document, text: str, chunks: list[str], starts: list[int]) -> list[str]:
        """What each chunk is embedded and keyword-indexed from."""
        suffix = Path(document.filename).suffix.lower()
        clean = text_cleanup_mode() != "off"
        boilerplate = frozenset()
        if clean and suffix not in STRUCTURED:
            boilerplate = await shared_lines(self.session, document.id, text)
        return embedding_texts(text, chunks, starts, suffix, clean=clean, boilerplate=boilerplate)

    async def _embed(self, document: Document, texts: list[str], *, report: bool = True) -> list[list[float]]:
        """Vectors of `texts`, in batches; `report`: as the document's
        progress, from 30 to 95%."""
        if report:
            await self._set(document, DocumentStatus.EMBEDDING, 30)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            vectors.extend(
                await asyncio.to_thread(self.embedder.embed_passages, texts[start : start + EMBED_BATCH_SIZE])
            )
            if report:
                done = min(start + EMBED_BATCH_SIZE, len(texts))
                await self._set(document, DocumentStatus.EMBEDDING, 30 + int(65 * done / len(texts)))
        return vectors

    async def _drop_index(self, document_id: int) -> None:
        """Removes the document's chunks from search; Qdrant being down must
        not hide the error being handled."""
        try:
            await self.rag.delete_document(document_id)
        except AppError:
            pass

    async def fail(self, document_id: int, message: str) -> None:
        document = await self._require(document_id)
        if document is None or document.status == DocumentStatus.COMPLETED:
            return
        await self._drop_index(document.id)
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
        if document.reindexing:
            # Was ready before: the file may be in another storage (STORAGE
            # changed without moving the files). Kept, failed, for a retry
            # once the file is back.
            document.file_missing = True
            document.reindexing = False
            await self.fail(document_id, "The document file is missing.")
            return
        await self._drop_index(document.id)
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
        row = (
            await self.session.execute(
                select(Document, User.language)
                .outerjoin(User, User.id == Document.user_id)
                .where(Document.id == document_id)
            )
        ).first()
        if row is None:
            return None
        # The owner reads what this job stores: the error and the notices.
        use_language(row.language)
        return row.Document

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
                select(Document.id).where(Document.status.not_in(DONE_STATUSES)).order_by(Document.id)
            )
            return list(ids)
    finally:
        await engine.dispose()


async def claim_rechunk() -> int | None:
    """The next document marked for re-chunking, unmarked as it is taken:
    whatever happens to it, the work moves on and never repeats it."""
    try:
        async with AsyncSessionLocal() as session:
            marked = (
                select(Document.id)
                .where(Document.reindexing.is_(True), Document.status == DocumentStatus.COMPLETED)
                .order_by(Document.id)
                .limit(1)
                .with_for_update(skip_locked=True)
                .scalar_subquery()
            )
            claimed = await session.scalar(
                update(Document).where(Document.id == marked).values(reindexing=False).returning(Document.id)
            )
            await session.commit()
            return claimed
    finally:
        await engine.dispose()


async def rechunk_document_job(document_id: int) -> None:
    await _with_processor(lambda processor: processor.rechunk(document_id))


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
