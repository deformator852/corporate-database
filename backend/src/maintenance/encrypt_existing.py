"""Encrypts data stored before encryption at rest was enabled.

    cd backend/src && uv run python -m maintenance.encrypt_existing

Safe to run repeatedly: values that are already encrypted are skipped.
Covers document files in MinIO, document text in Postgres and chunk text in
Qdrant.
"""

import asyncio
import io

from minio.error import S3Error
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy import select, text

from database import AsyncSessionLocal, engine
from encryption import encrypt_bytes, encrypt_text, is_encrypted_bytes, is_encrypted_text
from models.document import Document
from services.rag import COLLECTION_NAME, Rag, _chunk_context
from services.storage import ObjectStorage


async def _files() -> tuple[int, int]:
    storage = ObjectStorage()
    done = skipped = 0
    async with AsyncSessionLocal() as session:
        keys = list(await session.scalars(select(Document.object_key)))
    for key in keys:
        try:
            response = storage.client.get_object(storage.bucket, key)
            try:
                raw = response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error:
            skipped += 1  # missing file: nothing to protect
            continue
        if is_encrypted_bytes(raw):
            skipped += 1
            continue
        sealed = encrypt_bytes(raw, key)
        storage.client.put_object(storage.bucket, key, io.BytesIO(sealed), len(sealed))
        done += 1
    return done, skipped


async def _texts() -> int:
    # Raw SQL: the ORM column type would decrypt on read and hide the state.
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT document_id, text FROM document_texts "
                    "WHERE text NOT LIKE 'enc:v1:%'"
                )
            )
        ).all()
        for document_id, value in rows:
            await session.execute(
                text("UPDATE document_texts SET text = :value WHERE document_id = :id"),
                {"value": encrypt_text(value), "id": document_id},
            )
        await session.commit()
    return len(rows)


async def _chunks() -> int:
    rag = Rag()
    done = 0
    try:
        if not await rag.client.collection_exists(COLLECTION_NAME):
            return 0
        offset = None
        while True:
            records, offset = await rag.client.scroll(
                collection_name=COLLECTION_NAME,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                value = payload.get("text")
                if not isinstance(value, str) or is_encrypted_text(value):
                    continue
                context = _chunk_context(payload.get("document_id"), payload.get("chunk_index"))
                await rag.client.set_payload(
                    collection_name=COLLECTION_NAME,
                    payload={"text": encrypt_text(value, context)},
                    points=[record.id],
                )
                done += 1
            if offset is None:
                return done
    except UnexpectedResponse:
        return done
    finally:
        await rag.client.close()


async def main() -> None:
    try:
        files, skipped = await _files()
        texts = await _texts()
        chunks = await _chunks()
    finally:
        await engine.dispose()
    print(f"Encrypted {files} files ({skipped} already encrypted or missing),")
    print(f"{texts} document texts and {chunks} search chunks.")


if __name__ == "__main__":
    asyncio.run(main())
