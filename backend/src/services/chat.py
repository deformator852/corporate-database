import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.document import Document, DocumentStatus
from schemas.chat import ChatMessageSchema
from services.document_access import retrieval_classifications, user_permission_keys
from services.embedding import EmbeddingModel
from services.generator import OllamaGenerator
from services.parser import DocumentParser
from services.rag import Rag
from services.storage import ObjectStorage

_MAX_DOCS = 2
_MAX_CHARS = 100_000
_DUMP_MARKERS = (
    "full content",
    "full text",
    "entire content",
    "entire file",
    "whole file",
    "whole content",
    "verbatim",
    "полный текст",
    "полное содержимое",
    "весь файл",
    "целиком",
)


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingModel,
        generator: OllamaGenerator,
        storage: ObjectStorage,
    ) -> None:
        self.session = session
        self.embedder = embedder
        self.generator = generator
        self.storage = storage
        self.parser = DocumentParser()

    async def reply(
        self, user_id: int, messages: list[ChatMessageSchema]
    ) -> str:
        keys = await user_permission_keys(self.session, user_id)
        allowed = retrieval_classifications(keys)
        if not allowed:
            return await self.generator.complete(messages, [])
        query = messages[-1].content
        rag = Rag()
        try:
            vector = await asyncio.to_thread(self.embedder.embed_query, query)
            chunks = await rag.search(
                vector,
                allowed_classifications=allowed,
                limit=8,
            )
            documents = await self._documents_for_reply(
                query, chunks, allowed, rag
            )
        finally:
            await rag.client.close()
        if documents and _wants_full_document(query):
            return _dump(documents)
        return await self.generator.complete(messages, documents)

    async def _documents_for_reply(
        self,
        query: str,
        chunks: list[dict[str, object]],
        allowed: tuple[str, ...],
        rag: Rag,
    ) -> list[dict[str, object]]:
        named = await self._named_document_ids(query, allowed)
        ranked: list[int] = []
        seen: set[int] = set()
        for document_id in (*named, *(_document_id(chunk) for chunk in chunks)):
            if document_id is None or document_id in seen:
                continue
            seen.add(document_id)
            ranked.append(document_id)
        if not ranked:
            return []
        rows = {
            document.id: document
            for document in await self.session.scalars(
                select(Document).where(
                    Document.id.in_(ranked),
                    Document.classification.in_(allowed),
                    Document.status == DocumentStatus.COMPLETED,
                )
            )
        }
        loaded: list[dict[str, object]] = []
        for document_id in ranked:
            document = rows.get(document_id)
            if document is None:
                continue
            text = await self._document_text(document, rag)
            if not text:
                continue
            loaded.append(
                {
                    "document_id": document.id,
                    "name": document.name,
                    "filename": document.filename,
                    "text": text,
                }
            )
            if len(loaded) >= _MAX_DOCS:
                break
        return loaded

    async def _named_document_ids(
        self, query: str, allowed: tuple[str, ...]
    ) -> list[int]:
        needle = query.casefold()
        documents = await self.session.scalars(
            select(Document).where(
                Document.classification.in_(allowed),
                Document.status == DocumentStatus.COMPLETED,
            )
        )
        return [
            document.id
            for document in documents
            if document.filename.casefold() in needle
            or document.name.casefold() in needle
        ]

    async def _document_text(self, document: Document, rag: Rag) -> str:
        try:
            raw = await asyncio.to_thread(self.storage.get, document.object_key)
            text = await asyncio.to_thread(
                self.parser.parse, raw, document.filename
            )
        except AppError:
            payloads = await rag.payloads_for_document(document.id)
            text = "\n".join(
                str(payload.get("text") or "").strip()
                for payload in payloads
                if str(payload.get("text") or "").strip()
            )
        if len(text) > _MAX_CHARS:
            return text[:_MAX_CHARS].rstrip() + "\n…"
        return text


def _dump(documents: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for document in documents:
        name = str(document.get("filename") or document.get("name") or "Document")
        text = str(document.get("text") or "").strip()
        if not text:
            continue
        parts.append(f"{name}\n\n{text}")
    return "\n\n".join(parts)


def _wants_full_document(query: str) -> bool:
    lowered = query.casefold()
    return any(marker in lowered for marker in _DUMP_MARKERS)


def _document_id(chunk: dict[str, object]) -> int | None:
    raw = chunk.get("document_id")
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None
