import asyncio
from collections.abc import Sequence

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from i18n import t
from models.document import Document, DocumentStatus
from models.document_text import DocumentText
from schemas.chat import ChatMessageSchema
from services.chat.context_document import ContextDocument
from services.chat.excerpts import fit_to_context
from services.chat.generator import OllamaGenerator, OnDelta, document_budget_chars
from services.documents.access import retrieval_classifications, user_permission_keys
from services.search.embedding import EmbeddingModel
from services.search.rag import Rag, SearchHit
from settings import embedding_model

_MAX_DOCS = 2
_MAX_CHARS = 100_000
# A document name shorter than this is not looked for in the question.
_MIN_NAMED_LENGTH = 3
# Said without asking the model when no document passes the search: given
# only the chat history, a small model invents an answer that looks sourced.
NO_DOCUMENTS_ANSWER = "I don't know: none of the documents you can access answer this."
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
        *,
        document_ids: Sequence[int] = (),
    ) -> tuple[str, list[ContextDocument], list[ContextDocument]]:
        """Answer text, the documents it used (shown as sources) and every
        document the model read (for the audit log). Generated text also
        streams to `on_delta` as it arrives. `document_ids`, if any, are the
        only documents the answer may come from."""
        allowed = retrieval_classifications(await user_permission_keys(self.session, user_id))
        query = messages[-1].content
        documents: list[ContextDocument] = []
        prompt_documents: list[ContextDocument] = []
        if allowed:
            rag = Rag()
            try:
                hits = await self._search(_search_queries(messages), allowed, rag, document_ids)
                documents = await self._documents_for_reply(query, hits, allowed, document_ids)
                if documents and _wants_full_document(query):
                    return _dump(documents), documents, documents
                prompt_documents = await fit_to_context(documents, hits, rag, document_budget_chars(_MAX_DOCS))
            finally:
                await rag.client.close()
        if not documents:
            answer = t(NO_DOCUMENTS_ANSWER)
            if on_delta is not None:
                await on_delta(answer)
            return answer, [], []
        answer, used = await self.generator.complete(messages, prompt_documents, on_delta)
        used_ids = {document.document_id for document in used}
        return answer, [d for d in documents if d.document_id in used_ids], documents

    async def cite(self, user_id: int, answer: str, sources: Sequence[ContextDocument]) -> dict[int, int]:
        """For each source, the chunk closest to the answer: where the answer
        was taken from, shown when the source is opened. By the answer, not
        the question: a document named or chosen by the user has no search
        hits. Missing ones (search down) only lose the quote."""
        if not sources:
            return {}
        allowed = retrieval_classifications(await user_permission_keys(self.session, user_id))
        vector = await asyncio.to_thread(self.embedder.embed_query, answer)
        rag = Rag()
        found: dict[int, int] = {}
        try:
            for source in sources:
                hits = await rag.search(
                    vector, allowed_classifications=allowed, document_ids=[source.document_id], limit=1
                )
                if hits:
                    found[source.document_id] = hits[0].chunk_index
        except AppError:
            pass
        finally:
            await rag.client.close()
        return found

    async def _search(
        self, queries: list[str], allowed: tuple[str, ...], rag: Rag, document_ids: Sequence[int]
    ) -> list[SearchHit]:
        """Relevant hits of all `queries`, each chunk once with its best score.
        Chunks holding the question's names and codes come first. In documents
        the user chose every hit counts: they asked about those documents."""
        best: dict[tuple[int, int], SearchHit] = {}
        for query in queries:
            vector = await asyncio.to_thread(self.embedder.embed_query, query)
            found = await rag.search(
                vector, question=query, allowed_classifications=allowed, document_ids=document_ids, limit=8
            )
            for hit in found:
                key = (hit.document_id, hit.chunk_index)
                if key not in best or _rank(hit) < _rank(best[key]):
                    best[key] = hit
        ranked = sorted(best.values(), key=_rank)
        return ranked if document_ids else _relevant(ranked)

    async def _documents_for_reply(
        self, query: str, hits: list[SearchHit], allowed: tuple[str, ...], document_ids: Sequence[int]
    ) -> list[ContextDocument]:
        """Documents named in the question, then those of the hits, then the
        rest the user chose, in order; at most _MAX_DOCS, each with its saved
        text. Chosen documents leave out all others."""
        named = await self._named_document_ids(query, allowed)
        ranked = list(dict.fromkeys([*named, *(h.document_id for h in hits), *document_ids]))
        if document_ids:
            chosen = set(document_ids)
            ranked = [document_id for document_id in ranked if document_id in chosen]
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
        loaded: list[ContextDocument] = []
        for document_id in ranked:
            document = rows.get(document_id)
            text = await self._document_text(document_id) if document is not None else ""
            if document is None or not text:
                continue
            loaded.append(
                ContextDocument(
                    document_id=document.id,
                    name=document.name,
                    filename=document.filename,
                    classification=document.classification,
                    text=text,
                )
            )
            if len(loaded) >= _MAX_DOCS:
                break
        return loaded

    async def _named_document_ids(self, query: str, allowed: tuple[str, ...]) -> list[int]:
        # Documents whose name or filename appears in the question. Postgres
        # compares and returns ids only, instead of loading every document.
        # Names this short ("A", "HR") are inside almost any question.
        needle = literal(query.lower())
        ids = await self.session.scalars(
            select(Document.id).where(
                Document.classification.in_(allowed),
                Document.status == DocumentStatus.COMPLETED,
                or_(
                    and_(
                        func.length(Document.name) >= _MIN_NAMED_LENGTH,
                        func.strpos(needle, func.lower(Document.name)) > 0,
                    ),
                    func.strpos(needle, func.lower(Document.filename)) > 0,
                ),
            )
        )
        return list(ids)

    async def _document_text(self, document_id: int) -> str:
        """Saved at processing time; never parsed per question."""
        text = await self.session.scalar(select(DocumentText.text).where(DocumentText.document_id == document_id))
        return _cap(text or "")


def _search_queries(messages: list[ChatMessageSchema]) -> list[str]:
    """The question, and with the previous one for follow-ups such as "what
    about sales?", which alone match no document."""
    question = messages[-1].content
    earlier = [m.content for m in messages[:-1] if m.role == "user"]
    return [question, f"{earlier[-1]}\n{question}"] if earlier else [question]


def _rank(hit: SearchHit) -> tuple[bool, float]:
    """Sort key, best first: exact matches, then by score."""
    return (not hit.exact, -hit.score)


def _relevant(hits: list[SearchHit]) -> list[SearchHit]:
    """Hits that score at least the model's `min_score`, and keyword hits
    holding the question's names and codes (`exact`). Documents named in the
    question are found separately and do not need a score."""
    floor = embedding_model().min_score
    if floor is None:
        return hits
    return [hit for hit in hits if hit.exact or hit.score >= floor]


def _cap(text: str) -> str:
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS].rstrip() + "\n…"
    return text


def _dump(documents: list[ContextDocument]) -> str:
    return "\n\n".join(f"{d.label}\n\n{d.text.strip()}" for d in documents if d.text.strip())


def _wants_full_document(query: str) -> bool:
    lowered = query.casefold()
    return any(marker in lowered for marker in _DUMP_MARKERS)
