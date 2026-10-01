import asyncio

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.document import Document, DocumentStatus
from models.document_text import DocumentText
from schemas.chat import ChatMessageSchema
from services.documents.access import retrieval_classifications, user_permission_keys
from services.embedding import EmbeddingModel
from services.generator import OllamaGenerator, OnDelta, document_budget_chars
from services.rag import Rag
from settings import embedding_model

_MAX_DOCS = 2
# Chunks taken on each side of a search hit for excerpts of long documents.
_EXCERPT_RADIUS = 3
_MAX_CHARS = 100_000
_DUMP_MARKERS = (
    "full content",
    "full text",
    "entire content",
    "entire file",
    "whole file",
    "whole content",
    "verbatim",
    # es
    "texto completo",
    "contenido completo",
    "archivo completo",
    "íntegro",
    # fr
    "texte complet",
    "contenu complet",
    "fichier complet",
    "intégralité",
    "mot pour mot",
)


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingModel,
        generator: OllamaGenerator,
    ) -> None:
        self.session = session
        self.embedder = embedder
        self.generator = generator

    async def reply(
        self,
        user_id: int,
        messages: list[ChatMessageSchema],
        on_delta: OnDelta | None = None,
    ) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
        """Answer text, the documents it used (shown as sources) and every
        document the model read (for the audit log). Generated text also
        streams to `on_delta` as it arrives."""
        keys = await user_permission_keys(self.session, user_id)
        allowed = retrieval_classifications(keys)
        if not allowed:
            answer, _ = await self.generator.complete(messages, [], on_delta)
            return answer, [], []
        query = messages[-1].content
        rag = Rag()
        try:
            vector = await asyncio.to_thread(self.embedder.embed_query, query)
            chunks = _relevant(
                await rag.search(vector, allowed_classifications=allowed, limit=8)
            )
            documents = await self._documents_for_reply(
                query, chunks, allowed, rag
            )
            if documents and _wants_full_document(query):
                return _dump(documents), documents, documents
            prompt_documents = await self._fit_to_context(documents, chunks, rag)
        finally:
            await rag.client.close()
        answer, used = await self.generator.complete(messages, prompt_documents, on_delta)
        used_ids = {document["document_id"] for document in used}
        sources = [d for d in documents if d["document_id"] in used_ids]
        return answer, sources, documents

    async def _fit_to_context(
        self,
        documents: list[dict[str, object]],
        hits: list[dict[str, object]],
        rag: Rag,
    ) -> list[dict[str, object]]:
        """Documents as the LLM sees them. One too long for its share of the
        context is replaced by excerpts around the search hits, so a clause
        deep in a long contract still reaches the model (a cut from the start
        would drop it). Without hits it keeps the start of the text."""
        budget = document_budget_chars(_MAX_DOCS)
        fitted: list[dict[str, object]] = []
        for document in documents:
            text = str(document["text"])
            hit_indexes = [
                index
                for hit in hits
                if _document_id(hit) == document["document_id"]
                and isinstance(index := hit.get("chunk_index"), int)
            ]
            if len(text) <= budget or not hit_indexes:
                fitted.append(document)
                continue
            wanted = sorted(
                {
                    index + offset
                    for index in hit_indexes
                    for offset in range(-_EXCERPT_RADIUS, _EXCERPT_RADIUS + 1)
                    if index + offset >= 0
                }
            )
            chunks = await rag.chunks_by_index(int(document["document_id"]), wanted)
            excerpt = build_excerpt(chunks, hit_indexes, budget)
            if not excerpt:
                fitted.append(document)
                continue
            fitted.append(
                {**document, "text": "[Excerpts from a longer document]\n" + excerpt}
            )
        return fitted

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
            text = await self._document_text(document)
            if not text:
                continue
            loaded.append(
                {
                    "document_id": document.id,
                    "classification": document.classification,
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
        # Documents whose name or filename appears in the question. Postgres
        # compares and returns ids only, instead of loading every document.
        needle = literal(query.lower())
        ids = await self.session.scalars(
            select(Document.id).where(
                Document.classification.in_(allowed),
                Document.status == DocumentStatus.COMPLETED,
                or_(
                    func.strpos(needle, func.lower(Document.name)) > 0,
                    func.strpos(needle, func.lower(Document.filename)) > 0,
                ),
            )
        )
        return list(ids)

    async def _document_text(self, document: Document) -> str:
        """Saved at processing time; never parsed per question."""
        text = await self.session.scalar(
            select(DocumentText.text).where(DocumentText.document_id == document.id)
        )
        return _cap(text or "")


def _relevant(hits: list[dict[str, object]]) -> list[dict[str, object]]:
    """Hits that score at least the model's `min_score`. Documents named in
    the question are found separately and do not need a score."""
    floor = embedding_model().min_score
    if floor is None:
        return hits
    return [hit for hit in hits if float(hit.get("score") or 0) >= floor]


def _cap(text: str) -> str:
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


def build_excerpt(
    chunks: dict[int, tuple[str, int]], hits: list[int], budget: int
) -> str:
    """Hit chunks first, then their neighbours at distance 1, 2, ... while
    they fit `budget` characters; joined in document order without repeating
    the overlap between neighbours. Gaps are marked with "…"."""
    order: list[int] = list(dict.fromkeys(hits))
    for distance in range(1, _EXCERPT_RADIUS + 1):
        for hit in dict.fromkeys(hits):
            order += [hit - distance, hit + distance]
    selected: set[int] = set()
    used = 0
    for index in order:
        entry = chunks.get(index)
        if entry is None or index in selected or used + len(entry[0]) > budget:
            continue
        selected.add(index)
        used += len(entry[0])
    parts: list[str] = []
    previous: int | None = None
    for index in sorted(selected):
        text, start = chunks[index]
        if previous is not None and index == previous + 1:
            parts[-1] += _continuation(chunks[previous], (text, start))
        else:
            parts.append(text)
        previous = index
    return "\n…\n".join(part.strip() for part in parts)


def _continuation(before: tuple[str, int], after: tuple[str, int]) -> str:
    """`after` without the text it repeats from `before`, cut exactly by the
    chunks' start offsets in the document."""
    (before_text, before_start), (after_text, after_start) = before, after
    shared = before_start + len(before_text) - after_start
    if shared > 0:
        return after_text[shared:]
    # Not adjacent in the text (whitespace between chunks).
    return "\n" + after_text
