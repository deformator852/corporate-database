import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Any, NoReturn
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv
from httpx import RequestError
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.http.models import (
    CollectionStatus,
    Distance,
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchAny,
    MatchValue,
    Modifier,
    PayloadField,
    PayloadSchemaType,
    PointStruct,
    Range,
    ScoredPoint,
    SparseVectorParams,
    VectorParams,
)

from encryption import decrypt_text, encrypt_text
from exceptions import AppError
from services.search.keywords import chunk_keywords, holds, identifiers, query_keywords
from settings import embedding_model, qdrant_api_key

load_dotenv()

COLLECTION_NAME = "documents"
VECTOR_DISTANCE = Distance.COSINE
# Sparse vectors of chunk words, next to the dense one (services/search/keywords.py).
KEYWORDS = "keywords"
# Payload fields every search or delete filters on. Without an index Qdrant
# checks each candidate point's payload, which slows down as documents grow.
PAYLOAD_INDEXES = {
    "classification": PayloadSchemaType.KEYWORD,
    "document_id": PayloadSchemaType.INTEGER,
}
_indexes_ready = False


def _int_env(name: str) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else -1
    except ValueError as exc:
        raise AppError(
            "misconfigured",
            "Qdrant port is not configured.",
            status_code=500,
        ) from exc
    if value < 1 or value > 65535:
        raise AppError(
            "misconfigured",
            "Qdrant port is not configured.",
            status_code=500,
        )
    return value


def _qdrant_client() -> AsyncQdrantClient:
    host = (os.getenv("QDRANT_HOST") or "").strip()
    if not host:
        raise AppError(
            "misconfigured",
            "Qdrant host is not configured.",
            status_code=500,
        )
    # Plain HTTP on loopback/the compose network; the key still gates access.
    return AsyncQdrantClient(
        host=host,
        port=_int_env("QDRANT_PORT"),
        api_key=qdrant_api_key(),
        https=False,
    )


def _raise_conflict(message: str) -> NoReturn:
    raise AppError("conflict", message, status_code=409)


@asynccontextmanager
async def _qdrant_errors() -> AsyncIterator[None]:
    """Qdrant failures as AppError: rejected (403) or unreachable (503)."""
    try:
        yield
    except UnexpectedResponse as exc:
        if exc.status_code in {401, 403}:
            raise AppError("forbidden", "Qdrant rejected the request.", status_code=403) from exc
        raise AppError("unavailable", "Could not reach Qdrant.", status_code=503) from exc
    except (RequestError, ResponseHandlingException) as exc:
        raise AppError("unavailable", "Could not reach Qdrant.", status_code=503) from exc


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A chunk found by search. `score` is its cosine to the question;
    `exact`: it holds every name and code of the question (keyword search),
    which makes it relevant whatever the score."""

    document_id: int
    chunk_index: int
    text: str
    start: int
    score: float
    exact: bool = False


class Rag:
    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        self.client = client or _qdrant_client()
        self.vector_size = embedding_model().dims

    async def ensure_collection(self) -> None:
        async with _qdrant_errors():
            # Twice: another process may delete it between the two steps.
            for _ in range(2):
                if not await self.client.collection_exists(COLLECTION_NAME):
                    await self._create_if_absent()
                try:
                    await self._require_compatible()
                    await self._ensure_indexes()
                    return
                except UnexpectedResponse as exc:
                    if exc.status_code != 404:
                        raise
        _raise_conflict(f"Collection {COLLECTION_NAME} was not created.")

    async def _if_indexed[T](self, operation: Callable[[], Awaitable[T]], missing: T) -> T:
        """`operation` on the collection, or `missing` when there is none
        yet: nothing is indexed, so there is nothing to read or change."""
        async with _qdrant_errors():
            try:
                if await self.client.collection_exists(COLLECTION_NAME):
                    return await operation()
            except UnexpectedResponse as exc:
                if exc.status_code != 404:  # deleted meanwhile
                    raise
        return missing

    async def upsert_chunks(
        self,
        *,
        document_id: int,
        name: str,
        filename: str,
        classification: str,
        chunks: list[str],
        vectors: list[list[float]],
        starts: list[int],
        indexed: list[str],
    ) -> None:
        """`indexed`: the text each vector was made from, indexed by word."""
        await self.ensure_collection()
        points = [
            PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"document:{document_id}:{index}")),
                vector={"": vector, KEYWORDS: chunk_keywords(indexed[index])},
                payload={
                    "document_id": document_id,
                    "chunk_index": index,
                    # Encrypted at rest; vectors cannot be (search needs them).
                    "text": encrypt_text(chunk, _chunk_context(document_id, index)),
                    "name": name,
                    "filename": filename,
                    "classification": classification,
                    # Offset of the chunk in the cleaned text, for exact joins.
                    "start": starts[index],
                },
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        if not points:
            return
        async with _qdrant_errors():
            await self.client.upsert(collection_name=COLLECTION_NAME, points=points)

    async def update_document(self, document_id: int, *, name: str, classification: str) -> None:
        """New name and classification on every chunk of the document."""
        await self._if_indexed(
            lambda: self.client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"name": name, "classification": classification},
                points=_document_filter(document_id),
                wait=True,
            ),
            missing=None,
        )

    async def delete_chunks_from(self, document_id: int, first_index: int) -> None:
        """The document's chunks from `first_index` on: left over when it is
        cut into fewer chunks than before."""
        await self._if_indexed(
            lambda: self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                        FieldCondition(key="chunk_index", range=Range(gte=first_index)),
                    ]
                ),
            ),
            missing=None,
        )

    async def delete_document(self, document_id: int) -> None:
        await self._if_indexed(
            lambda: self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=_document_filter(document_id),
            ),
            missing=None,
        )

    async def search(
        self,
        vector: list[float],
        *,
        question: str = "",
        allowed_classifications: Sequence[str],
        document_ids: Sequence[int] = (),
        limit: int = 8,
    ) -> list[SearchHit]:
        """Chunks closest to `vector`, each with its cosine `score`, plus
        chunks holding every identifier of `question` (keywords.identifiers)
        found by keyword. Those are marked `exact`: they count as relevant
        whatever their score. `document_ids`, if any, limit the search to
        those documents."""
        if not allowed_classifications or limit < 1:
            return []
        query_filter = self._classification_filter(allowed_classifications)
        if document_ids:
            query_filter = Filter(
                must=[query_filter, FieldCondition(key="document_id", match=MatchAny(any=list(document_ids)))]
            )
        wanted = identifiers(question)

        async def query() -> tuple[list[ScoredPoint], list[ScoredPoint]]:
            by_vector = await self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            if not wanted:
                return by_vector.points, []
            by_keyword = await self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_keywords(question),
                using=KEYWORDS,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=[""],
            )
            return by_vector.points, by_keyword.points

        vector_points, keyword_points = await self._if_indexed(query, missing=([], []))
        found: dict[object, SearchHit] = {}
        for point in vector_points:
            if (hit := _hit(point.payload, point.score)) is not None:
                found[point.id] = hit
        for point in keyword_points:
            # Its cosine, to rank it with the vector hits.
            hit = found.get(point.id) or _hit(point.payload, _cosine(vector, point.vector))
            if hit is not None and holds(hit.text, wanted):
                found[point.id] = replace(hit, exact=True)
        return list(found.values())

    async def chunks_by_index(self, document_id: int, indexes: Sequence[int]) -> dict[int, tuple[str, int]]:
        """Text and start offset of the document's chunks at `indexes`;
        missing ones are left out."""
        if not indexes:
            return {}
        records, _offset = await self._if_indexed(
            lambda: self.client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                        FieldCondition(key="chunk_index", match=MatchAny(any=list(indexes))),
                    ]
                ),
                limit=len(indexes),
                with_payload=True,
                with_vectors=False,
            ),
            missing=([], None),
        )
        found: dict[int, tuple[str, int]] = {}
        for record in records:
            if (hit := _hit(record.payload, 0.0)) is not None:
                found[hit.chunk_index] = (hit.text, hit.start)
        return found

    def _classification_filter(self, allowed_classifications: Sequence[str]) -> Filter:
        allowed = list(allowed_classifications)
        should: list[FieldCondition | IsEmptyCondition] = [
            FieldCondition(
                key="classification",
                match=MatchAny(any=allowed),
            )
        ]
        if "standard" in allowed:
            should.append(IsEmptyCondition(is_empty=PayloadField(key="classification")))
        return Filter(should=should)

    async def _ensure_indexes(self) -> None:
        # Creating an existing index is a no-op; once per process is enough.
        global _indexes_ready
        if _indexes_ready:
            return
        for field_name, schema in PAYLOAD_INDEXES.items():
            await self.client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=schema,
                wait=True,
            )
        _indexes_ready = True

    async def _create_if_absent(self) -> None:
        try:
            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=VECTOR_DISTANCE,
                ),
                # Qdrant weighs each word by how rare it is (IDF).
                sparse_vectors_config={KEYWORDS: SparseVectorParams(modifier=Modifier.IDF)},
            )
        except UnexpectedResponse as exc:
            if exc.status_code == 409:
                return
            raise

    async def _require_compatible(self) -> None:
        info = await self.client.get_collection(COLLECTION_NAME)
        if info.status == CollectionStatus.RED:
            raise AppError(
                "unavailable",
                "Qdrant collection is not ready.",
                status_code=503,
            )
        if self._vectors_match(info.config.params.vectors) and KEYWORDS in (info.config.params.sparse_vectors or {}):
            return
        if (info.points_count or 0) == 0:
            global _indexes_ready
            await self.client.delete_collection(COLLECTION_NAME)
            _indexes_ready = False
            await self._create_if_absent()
            return
        if not self._vectors_match(info.config.params.vectors):
            self._raise_vector_conflict(info.config.params.vectors)
        _raise_conflict(
            f"Collection {COLLECTION_NAME} has no keyword index; it was made by an "
            "older version. Recreate it and process the documents again."
        )

    def _vectors_match(self, vectors: object) -> bool:
        if not isinstance(vectors, VectorParams):
            return False
        distance = vectors.distance if isinstance(vectors.distance, Distance) else Distance(str(vectors.distance))
        return vectors.size == self.vector_size and distance == VECTOR_DISTANCE

    def _raise_vector_conflict(self, vectors: object) -> None:
        if not isinstance(vectors, VectorParams):
            _raise_conflict(
                f"Collection {COLLECTION_NAME} already exists with named vectors; "
                f"expected a single dense vector of size {self.vector_size} "
                f"and {VECTOR_DISTANCE.value} distance."
            )
        distance = vectors.distance if isinstance(vectors.distance, Distance) else Distance(str(vectors.distance))
        _raise_conflict(
            f"Collection {COLLECTION_NAME} already exists with size {vectors.size} "
            f"and {distance.value} distance; expected size {self.vector_size} "
            f"and {VECTOR_DISTANCE.value} distance."
        )


def _cosine(query: list[float], stored: object) -> float:
    """Both vectors are normalized by the embedding model. `stored` is the
    point's vector: a list, or named vectors where "" is the dense one."""
    if isinstance(stored, dict):
        stored = stored.get("")
    if not isinstance(stored, list):
        return 0.0
    return float(sum(a * b for a, b in zip(query, stored, strict=False)))


def _document_filter(document_id: int) -> Filter:
    return Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))])


def _chunk_context(document_id: int, index: int) -> str:
    return f"chunk:{document_id}:{index}"


def _hit(payload: dict[str, Any] | None, score: float) -> SearchHit | None:
    """The chunk a point stores, its text decrypted; None for a point that
    is not one of ours."""
    payload = payload or {}
    document_id, index, start, text = (payload.get(key) for key in ("document_id", "chunk_index", "start", "text"))
    if not (
        isinstance(document_id, int) and isinstance(index, int) and isinstance(start, int) and isinstance(text, str)
    ):
        return None
    return SearchHit(document_id, index, decrypt_text(text, _chunk_context(document_id, index)), start, score)
