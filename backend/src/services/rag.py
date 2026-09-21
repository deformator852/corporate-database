import os
from typing import NoReturn
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
    MatchValue,
    PointStruct,
    VectorParams,
)

from exceptions import AppError
from settings import embedding_vector_size

load_dotenv()

COLLECTION_NAME = "documents"
VECTOR_DISTANCE = Distance.COSINE


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
    return AsyncQdrantClient(host=host, port=_int_env("QDRANT_PORT"))


def _raise_unavailable(exc: Exception) -> NoReturn:
    raise AppError(
        "unavailable",
        "Could not reach Qdrant.",
        status_code=503,
    ) from exc


def _raise_conflict(message: str) -> NoReturn:
    raise AppError("conflict", message, status_code=409)


def _raise_from_unexpected(exc: UnexpectedResponse) -> NoReturn:
    if exc.status_code in {401, 403}:
        raise AppError(
            "forbidden",
            "Qdrant rejected the request.",
            status_code=403,
        ) from exc
    _raise_unavailable(exc)


class Rag:
    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        self.client = client or _qdrant_client()
        self.vector_size = embedding_vector_size()

    async def ensure_collection(self) -> None:
        try:
            for _ in range(2):
                if not await self.client.collection_exists(COLLECTION_NAME):
                    await self._create_if_absent()
                try:
                    await self._require_compatible()
                    return
                except UnexpectedResponse as exc:
                    if exc.status_code == 404:
                        continue
                    raise
            _raise_conflict(f"Collection {COLLECTION_NAME} was not created.")
        except AppError:
            raise
        except UnexpectedResponse as exc:
            _raise_from_unexpected(exc)
        except (RequestError, ResponseHandlingException) as exc:
            _raise_unavailable(exc)

    async def upsert_chunks(
        self,
        *,
        document_id: int,
        name: str,
        filename: str,
        chunks: list[str],
        vectors: list[list[float]],
    ) -> None:
        await self.ensure_collection()
        points = [
            PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"document:{document_id}:{index}")),
                vector=vector,
                payload={
                    "document_id": document_id,
                    "chunk_index": index,
                    "text": chunk,
                    "name": name,
                    "filename": filename,
                },
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        if not points:
            return
        try:
            await self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        except UnexpectedResponse as exc:
            _raise_from_unexpected(exc)
        except (RequestError, ResponseHandlingException) as exc:
            _raise_unavailable(exc)

    async def delete_document(self, document_id: int) -> None:
        try:
            if not await self.client.collection_exists(COLLECTION_NAME):
                return
            await self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                ),
            )
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                return
            _raise_from_unexpected(exc)
        except (RequestError, ResponseHandlingException) as exc:
            _raise_unavailable(exc)

    async def _create_if_absent(self) -> None:
        try:
            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=VECTOR_DISTANCE,
                ),
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
        if self._vectors_match(info.config.params.vectors):
            return
        if (info.points_count or 0) == 0:
            await self.client.delete_collection(COLLECTION_NAME)
            await self._create_if_absent()
            return
        self._raise_vector_conflict(info.config.params.vectors)

    def _vectors_match(self, vectors: object) -> bool:
        if not isinstance(vectors, VectorParams):
            return False
        distance = (
            vectors.distance
            if isinstance(vectors.distance, Distance)
            else Distance(str(vectors.distance))
        )
        return vectors.size == self.vector_size and distance == VECTOR_DISTANCE

    def _raise_vector_conflict(self, vectors: object) -> None:
        if not isinstance(vectors, VectorParams):
            _raise_conflict(
                f"Collection {COLLECTION_NAME} already exists with named vectors; "
                f"expected a single dense vector of size {self.vector_size} "
                f"and {VECTOR_DISTANCE.value} distance."
            )
        distance = (
            vectors.distance
            if isinstance(vectors.distance, Distance)
            else Distance(str(vectors.distance))
        )
        _raise_conflict(
            f"Collection {COLLECTION_NAME} already exists with size {vectors.size} "
            f"and {distance.value} distance; expected size {self.vector_size} "
            f"and {VECTOR_DISTANCE.value} distance."
        )
