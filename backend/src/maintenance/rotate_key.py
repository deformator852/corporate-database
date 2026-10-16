"""Re-encrypts all stored data with DATA_ENCRYPTION_KEY.

    deploy/deploy.sh rotate-key                                    (production)
    cd backend/src && uv run python -m maintenance.rotate_key      (development)

Rotation: `uv run setup key rotate` moves the key to
DATA_ENCRYPTION_KEY_PREVIOUS and generates a new one; this command then
re-encrypts document files (disk or S3), every encrypted column in Postgres (document
text, chats, the error log) and chunk text (Qdrant), and records the new key's fingerprint. DATA_ENCRYPTION_KEY_PREVIOUS
is then no longer needed: deploy.sh removes it from .env; in development
remove it by hand.

Resumable: values already sealed with the new key are skipped, so after a
failure fix the cause and run it again. Stop the backend and the worker first:
they would keep writing while it runs.
"""

import asyncio
from collections.abc import Callable

from sqlalchemy import select, text

import models  # noqa: F401 - every table, for encrypted_columns
from database import AsyncSessionLocal, Base, engine
from encryption import (
    EncryptedText,
    current_fingerprint,
    current_text_prefix,
    is_current_bytes,
    previous_fingerprint,
    reencrypt_bytes,
    reencrypt_text,
)
from exceptions import AppError
from extensions import plugins
from models.document import Document
from services.encryption_key import save_fingerprint, stored_fingerprint
from services.search.rag import COLLECTION_NAME, Rag, _chunk_context
from services.storage import ObjectStorage

_BATCH = 500


def encrypted_columns() -> list[tuple[str, str, str]]:
    """(table, primary key, column) of every EncryptedText column, those of
    extensions too; EncryptedText seals without a context."""
    plugins()  # registers the models of custom/ packages
    found = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, EncryptedText):
                (key,) = table.primary_key.columns
                found.append((table.name, key.name, column.name))
    return found


async def _check_keys() -> None:
    stored = await _stored()
    allowed = {current_fingerprint(), previous_fingerprint()}
    if stored is not None and stored not in allowed:
        raise AppError(
            "misconfigured",
            f"The stored data belongs to the key with fingerprint {stored}; "
            "neither DATA_ENCRYPTION_KEY nor DATA_ENCRYPTION_KEY_PREVIOUS is that key.",
            status_code=500,
        )


async def _stored() -> str | None:
    async with AsyncSessionLocal() as session:
        return await stored_fingerprint(session)


async def _files(report: Callable[[str], None]) -> int:
    storage = ObjectStorage()
    done = 0
    async with AsyncSessionLocal() as session:
        keys = list(await session.scalars(select(Document.object_key)))
    for key in keys:
        try:
            raw = storage.read_sealed(key)
        except AppError as exc:
            if exc.code == "not_found":
                continue  # missing file: nothing to protect
            raise
        if is_current_bytes(raw):
            continue
        storage.write_sealed(key, reencrypt_bytes(raw, key))
        done += 1
        if done % 100 == 0:
            report(f"  {done} files...")
    return done


async def _column(table: str, key: str, column: str) -> int:
    # Raw SQL: the ORM column type would decrypt on read and hide the state.
    # Re-encrypted rows start with the current prefix, so each batch fetches
    # only what is left and the loop ends.
    done = 0
    select_sql = text(
        f"SELECT {key}, {column} FROM {table} WHERE {column} NOT LIKE :prefix ORDER BY {key} LIMIT {_BATCH}"
    )
    update_sql = text(f"UPDATE {table} SET {column} = :value WHERE {key} = :id")
    prefix = current_text_prefix() + "%"
    while True:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(select_sql, {"prefix": prefix})).all()
            if not rows:
                return done
            for row_id, value in rows:
                await session.execute(update_sql, {"value": reencrypt_text(value), "id": row_id})
            await session.commit()
        done += len(rows)


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
                value, document_id, index = (payload.get(key) for key in ("text", "document_id", "chunk_index"))
                if not (isinstance(value, str) and isinstance(document_id, int) and isinstance(index, int)):
                    continue
                context = _chunk_context(document_id, index)
                sealed = reencrypt_text(value, context)
                if sealed == value:
                    continue
                await rag.client.set_payload(
                    collection_name=COLLECTION_NAME,
                    payload={"text": sealed},
                    points=[record.id],
                )
                done += 1
            if offset is None:
                return done
    finally:
        await rag.client.close()


async def reencrypt_all(report: Callable[[str], None] = print) -> None:
    await _check_keys()
    report(f"Key fingerprint: {current_fingerprint()}")
    report(f"Files: {await _files(report)} re-encrypted")
    for table, key, column in encrypted_columns():
        report(f"{table}.{column}: {await _column(table, key, column)} re-encrypted")
    report(f"Search chunks: {await _chunks()} re-encrypted")
    async with AsyncSessionLocal() as session:
        await save_fingerprint(session, current_fingerprint())
    report("Done: all data is encrypted with the current key.")


async def main() -> None:
    try:
        await reencrypt_all()
    except AppError as exc:
        raise SystemExit(f"Stopped: {exc.message}") from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
