from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from i18n import t
from models.document import DONE_STATUSES, Document, DocumentStatus
from schemas.document import DocumentUploadSchema
from services.documents.access import (
    classifications_for_user,
    retrieval_classifications,
    user_permission_keys,
)
from services.documents.office import convert_doc_to_docx
from services.notifications.notification import NotificationService
from services.rag import Rag
from services.storage import ObjectStorage
from services.documents.upload_check import check_upload

ALLOWED_SUFFIXES = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".txt",
        ".odt",
        ".xlsx",
        ".csv",
        ".xml",
        ".json",
        ".md",
        ".mdx",
    }
)
DOC_SUFFIX = ".doc"
MAX_BYTES = 32 * 1024 * 1024
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


class DocumentJobQueue(Protocol):
    def enqueue(self, document_id: int) -> None: ...


class CeleryDocumentQueue:
    def enqueue(self, document_id: int) -> None:
        from tasks.document import process_document

        process_document.delay(document_id)


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
        self, user_id: int, page: int = 1, per_page: int = 20
    ) -> tuple[list[Document], int]:
        allowed = await self._allowed(user_id)
        visible = Document.classification.in_(allowed)
        total = await self.session.scalar(
            select(func.count()).select_from(Document).where(visible)
        )
        documents = await self.session.scalars(
            select(Document)
            .where(visible)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(documents), total or 0

    async def accept_upload(
        self,
        data: DocumentUploadSchema,
        user_id: int,
    ) -> tuple[Document, bool]:
        original_name = (data.file.filename or "").strip()
        suffix = Path(original_name).suffix.lower()
        if not original_name or suffix not in ALLOWED_SUFFIXES:
            raise AppError(
                "invalid",
                "This file type is not supported.",
                status_code=400,
            )

        try:
            classification = data.classification.value
            allowed = await self._allowed(user_id)
            if classification not in allowed:
                raise AppError("forbidden", "Insufficient permissions", status_code=403)
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
                    "Too many of your documents are waiting to be processed. "
                    "Upload more when some are ready.",
                    status_code=429,
                )
            content = await data.file.read(MAX_BYTES + 1)
            if not content:
                raise AppError("invalid", "The file is empty.", status_code=400)
            if len(content) > MAX_BYTES:
                raise AppError("invalid", "The file is too large.", status_code=400)
            converted = suffix == DOC_SUFFIX
            filename = Path(original_name).name
            if converted:
                filename = str(Path(filename).with_suffix(".docx"))
                if content.startswith(b"PK\x03\x04"):
                    # A .docx renamed to .doc, which Word opens as is.
                    suffix = ".docx"
            check_upload(content, suffix)
            if suffix == DOC_SUFFIX:
                content = await convert_doc_to_docx(content)
                suffix = ".docx"

            content_type = CONTENT_TYPES.get(suffix, "application/octet-stream")
            object_key = self.storage.make_key()
            document = Document(
                name=data.name,
                filename=filename,
                content_type=content_type,
                size=len(content),
                status=DocumentStatus.QUEUED,
                progress=0,
                object_key=object_key,
                classification=classification,
                user_id=user_id,
            )
            self.session.add(document)
            await self.session.commit()
            await self.session.refresh(document)
            try:
                await asyncio.to_thread(
                    self.storage.put,
                    key=object_key,
                    content=content,
                    content_type=content_type,
                )
            except Exception:
                await self._delete_row(document)
                try:
                    await asyncio.to_thread(self.storage.delete, object_key)
                except AppError:
                    pass
                raise
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
            return document, converted
        finally:
            await data.file.close()

    async def delete_document(self, document_id: int, user_id: int) -> Document:
        document = await self.session.scalar(
            select(Document).where(Document.id == document_id)
        )
        if document is None:
            raise AppError("not_found", "Document not found", status_code=404)
        allowed = await self._allowed(user_id)
        if document.classification not in allowed:
            raise AppError("not_found", "Document not found", status_code=404)
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
        allowed = retrieval_classifications(
            await user_permission_keys(self.session, user_id)
        )
        document = await self.session.get(Document, document_id)
        # 404 for both missing and forbidden: do not reveal what exists.
        if document is None or document.classification not in allowed:
            raise AppError("not_found", "Document not found", status_code=404)
        content = await asyncio.to_thread(self.storage.get, document.object_key)
        return document, content

    async def _allowed(self, user_id: int) -> tuple[str, ...]:
        return await classifications_for_user(self.session, user_id)

    async def _delete_row(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.commit()
