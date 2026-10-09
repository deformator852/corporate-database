from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from encryption import keyed_digest
from exceptions import AppError
from i18n import t
from models.document import DONE_STATUSES, Document, DocumentStatus
from models.document_text import DocumentText
from schemas.document import DocumentUpdateSchema, DocumentUploadSchema
from services.documents.access import (
    classifications_for_user,
    retrieval_classifications,
    user_permission_keys,
)
from services.documents.events import DocumentEventPublisher
from services.documents.office import convert_doc_to_docx
from services.documents.parser import PAGE_BREAK
from services.documents.upload_check import check_upload
from services.notifications.notification import NotificationService
from services.search.rag import Rag
from services.storage import ObjectStorage
from services.text_search import contains

DOC_SUFFIX = ".doc"
MAX_BYTES = 32 * 1024 * 1024
# Queued and every processing step count as "processing".
type DocumentStatusFilter = Literal["processing", "completed", "failed"]
# Documents of one user queued or in processing at once. The single worker
# takes them in turn, so a huge batch would hold up everyone else's uploads.
MAX_WAITING_DOCUMENTS = 100
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".xml": "application/xml",
    ".json": "application/json",
    ".md": "text/markdown",
    ".mdx": "text/markdown",
}
# A new file type needs a content type here, a check (upload_check.py) and an
# extractor (parser.py).
ALLOWED_SUFFIXES = frozenset(CONTENT_TYPES)


# Saved chat answers list their sources as [{id, name, filename}]; they show
# the document's current name.
_RENAME_IN_CHAT_SOURCES = text(
    """
    UPDATE chat_messages SET sources = (
        SELECT jsonb_agg(
            CASE WHEN (source->>'id')::int = CAST(:id AS int)
                THEN jsonb_set(source, '{name}', to_jsonb(CAST(:name AS text)))
                ELSE source END
            ORDER BY position)
        FROM jsonb_array_elements(sources) WITH ORDINALITY AS item(source, position)
    )
    WHERE sources @> jsonb_build_array(jsonb_build_object('id', CAST(:id AS int)))
    """
)


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    text: str
    # 1-based PDF page the chunk starts on; None for other files.
    page: int | None


@dataclass(frozen=True, slots=True)
class DocumentRevision:
    """A document's name and classification at one moment."""

    name: str
    classification: str


@dataclass(frozen=True, slots=True)
class DocumentFilter:
    """What the documents list shows; empty fields filter nothing."""

    # Part of the name or the file name.
    query: str = ""
    status: DocumentStatusFilter | None = None
    classification: str | None = None

    def conditions(self) -> list[ColumnElement[bool]]:
        found = contains(self.query, Document.name, Document.filename)
        if self.status == "processing":
            found.append(Document.status.not_in(DONE_STATUSES))
        elif self.status is not None:
            found.append(Document.status == self.status)
        if self.classification is not None:
            found.append(Document.classification == self.classification)
        return found


class DocumentJobQueue(Protocol):
    def enqueue(self, document_id: int) -> None: ...


class CeleryDocumentQueue:
    def enqueue(self, document_id: int) -> None:
        from tasks.document import process_document

        process_document.delay(document_id)


async def _read_upload(data: DocumentUploadSchema) -> bytes:
    content = await data.file.read(MAX_BYTES + 1)
    if not content:
        raise AppError("invalid", "The file is empty.", status_code=400)
    if len(content) > MAX_BYTES:
        raise AppError("invalid", "The file is too large.", status_code=400)
    return content


async def _stored_file(original_name: str, content: bytes) -> tuple[str, str, bytes]:
    """Filename, suffix and content to store, after checking the content
    matches the type. A .doc is stored as .docx: converted, or as is when it
    is a .docx renamed to .doc (Word opens both)."""
    filename = Path(original_name).name
    suffix = Path(original_name).suffix.lower()
    if suffix != DOC_SUFFIX:
        check_upload(content, suffix)
        return filename, suffix, content
    docx_name = str(Path(filename).with_suffix(".docx"))
    if content.startswith(b"PK\x03\x04"):
        check_upload(content, ".docx")
        return docx_name, ".docx", content
    check_upload(content, DOC_SUFFIX)
    return docx_name, ".docx", await convert_doc_to_docx(content)


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        storage: ObjectStorage,
        queue: DocumentJobQueue | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.queue = queue or CeleryDocumentQueue()

    async def list_documents(
        self, user_id: int, page: int = 1, per_page: int = 20, filters: DocumentFilter | None = None
    ) -> tuple[list[Document], int]:
        conditions = [
            Document.classification.in_(await self._allowed(user_id)),
            *(filters or DocumentFilter()).conditions(),
        ]
        total = await self.session.scalar(select(func.count()).select_from(Document).where(*conditions))
        documents = await self.session.scalars(
            select(Document)
            .where(*conditions)
            # Failed first: they wait for someone to retry or delete them.
            .order_by((Document.status == DocumentStatus.FAILED).desc(), Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(documents), total or 0

    async def accept_upload(
        self,
        data: DocumentUploadSchema,
        user_id: int,
    ) -> tuple[Document, bool]:
        """The new document, queued, and whether a .doc was converted."""
        try:
            original_name = (data.file.filename or "").strip()
            if not original_name or Path(original_name).suffix.lower() not in ALLOWED_SUFFIXES:
                raise AppError("invalid", "This file type is not supported.", status_code=400)
            classification = data.classification.value
            allowed = await self._allowed(user_id)
            if classification not in allowed:
                raise AppError("forbidden", "Insufficient permissions", status_code=403)
            await self._ensure_queue_room(user_id)
            content = await _read_upload(data)
            digest = keyed_digest(b"file:" + content)
            await self._refuse_duplicate(digest, allowed)
            filename, suffix, content = await _stored_file(original_name, content)
            document = Document(
                name=data.name,
                filename=filename,
                content_type=CONTENT_TYPES[suffix],
                size=len(content),
                status=DocumentStatus.QUEUED,
                progress=0,
                object_key=self.storage.make_key(),
                classification=classification,
                content_digest=digest,
                user_id=user_id,
            )
            await self._store(document, content)
            await self._enqueue(document)
            return document, Path(original_name).suffix.lower() == DOC_SUFFIX
        finally:
            await data.file.close()

    async def _store(self, document: Document, content: bytes) -> None:
        """The row, then the file; a file that cannot be saved takes the row
        with it."""
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        try:
            await asyncio.to_thread(
                self.storage.put,
                key=document.object_key,
                content=content,
                content_type=document.content_type,
            )
        except Exception:
            await self._delete_row(document)
            try:
                await asyncio.to_thread(self.storage.delete, document.object_key)
            except AppError:
                pass
            raise

    async def retry_document(self, document_id: int, user_id: int) -> Document:
        """Queues a failed document again; its file is still stored."""
        document = await self._visible(document_id, await self._allowed(user_id))
        if document.status != DocumentStatus.FAILED:
            raise AppError("conflict", "Only a failed document can be processed again.", status_code=409)
        await self._ensure_queue_room(user_id)
        document.status = DocumentStatus.QUEUED
        document.progress = 0
        document.error_message = None
        await self.session.commit()
        await self._enqueue(document)
        await self._publish(document)
        return document

    async def update_document(
        self, document_id: int, user_id: int, changes: DocumentUpdateSchema
    ) -> tuple[Document, DocumentRevision]:
        """Renames the document or changes its classification, in Postgres and
        on its search chunks in Qdrant. Returns the document and what it was."""
        allowed = await self._allowed(user_id)
        document = await self._visible(document_id, allowed)
        previous = DocumentRevision(document.name, document.classification)
        if document.status not in DONE_STATUSES:
            # The worker writes the chunks with the values it read at the start.
            raise AppError("conflict", "Wait until the document is processed.", status_code=409)
        classification = changes.classification.value if changes.classification else document.classification
        if classification not in allowed:
            raise AppError("forbidden", "Insufficient permissions", status_code=403)
        document.name = changes.name or document.name
        document.classification = classification
        if previous == DocumentRevision(document.name, document.classification):
            return document, previous
        if document.name != previous.name:
            await self.session.execute(_RENAME_IN_CHAT_SOURCES, {"id": document.id, "name": document.name})
        if document.status == DocumentStatus.COMPLETED:
            # Before the commit: if Qdrant fails, Postgres keeps the old values.
            rag = Rag()
            try:
                await rag.update_document(document.id, name=document.name, classification=classification)
            finally:
                await rag.client.close()
        await self.session.commit()
        await self._publish(document)
        return document, previous

    async def delete_document(self, document_id: int, user_id: int) -> Document:
        document = await self._visible(document_id, await self._allowed(user_id))
        rag = Rag()
        try:
            await rag.delete_document(document.id)
            await asyncio.to_thread(self.storage.delete, document.object_key)
            await self.session.delete(document)
            await self.session.commit()
        finally:
            await rag.client.close()
        if document.user_id is not None:
            # It may have been the last one the owner's ready notice waited for.
            await NotificationService(self.session).announce_ready(document.user_id)
        return document

    async def open_file(self, document_id: int, user_id: int) -> tuple[Document, bytes]:
        """The original file, for anyone who may retrieve documents of its
        classification (the same rule as chat answers)."""
        allowed = retrieval_classifications(await user_permission_keys(self.session, user_id))
        document = await self.session.get(Document, document_id)
        # 404 for both missing and forbidden: do not reveal what exists.
        if document is None or document.classification not in allowed:
            raise AppError("not_found", "Document not found", status_code=404)
        content = await asyncio.to_thread(self.storage.get, document.object_key)
        return document, content

    async def read_chunk(self, document_id: int, user_id: int, index: int) -> tuple[Document, DocumentChunk]:
        """A chunk of the document as stored for search, for showing where an
        answer came from; same clearance rule as opening the file."""
        allowed = retrieval_classifications(await user_permission_keys(self.session, user_id))
        document = await self._visible(document_id, allowed)
        rag = Rag()
        try:
            found = await rag.chunks_by_index(document.id, [index])
        finally:
            await rag.client.close()
        if index not in found:
            raise AppError("not_found", "Fragment not found", status_code=404)
        text, start = found[index]
        page = None
        if Path(document.filename).suffix.lower() == ".pdf":
            full = await self.session.scalar(select(DocumentText.text).where(DocumentText.document_id == document.id))
            page = (full or "")[:start].count(PAGE_BREAK) + 1
        return document, DocumentChunk(text=text, page=page)

    async def _refuse_duplicate(self, digest: bytes, allowed: tuple[str, ...]) -> None:
        """The same file twice only clutters search. Checked among documents
        the user may see: naming a hidden one would reveal that it exists."""
        name = await self.session.scalar(
            select(Document.name)
            .where(Document.content_digest == digest, Document.classification.in_(allowed))
            .limit(1)
        )
        if name is not None:
            raise AppError("conflict", 'This file is already uploaded as "{name}".', status_code=409, name=name)

    async def _allowed(self, user_id: int) -> tuple[str, ...]:
        return await classifications_for_user(self.session, user_id)

    async def _visible(self, document_id: int, allowed: tuple[str, ...]) -> Document:
        document = await self.session.get(Document, document_id)
        # 404 for both missing and forbidden: do not reveal what exists.
        if document is None or document.classification not in allowed:
            raise AppError("not_found", "Document not found", status_code=404)
        return document

    async def _ensure_queue_room(self, user_id: int) -> None:
        waiting = await self.session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.user_id == user_id,
                Document.status.not_in(DONE_STATUSES),
            )
        )
        if (waiting or 0) >= MAX_WAITING_DOCUMENTS:
            raise AppError(
                "rate_limited",
                "Too many of your documents are waiting to be processed. Upload more when some are ready.",
                status_code=429,
            )

    async def _enqueue(self, document: Document) -> None:
        try:
            self.queue.enqueue(document.id)
        except Exception as exc:
            document.status = DocumentStatus.FAILED
            document.error_message = t("Could not queue the document.")
            await self.session.commit()
            raise AppError(
                "unavailable",
                "Could not queue the document.",
                status_code=503,
            ) from exc

    async def _publish(self, document: Document) -> None:
        """Shows the change in other open document lists; they reload anyway."""
        await self.session.refresh(document)
        events = DocumentEventPublisher()
        try:
            await events.publish(document)
        except Exception:  # noqa: BLE001 - live view only, like the worker's events
            pass
        finally:
            await events.close()

    async def _delete_row(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.commit()
