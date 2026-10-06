"""Which DATA_ENCRYPTION_KEY the stored data belongs to.

The key's fingerprint (not the key) is kept in `system_state`. The backend and
the worker refuse to start with another key: a restored-from-memory or
regenerated key would otherwise write new data nobody can read together with
the old, and fail on every old document only when someone opens it.
"""

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from encryption import current_fingerprint, decrypt_text, previous_fingerprint
from exceptions import AppError
from models.system_state import SystemState

FINGERPRINT = "encryption_key_fingerprint"

# One encrypted value per table is enough to prove the key on first start.
_SAMPLES = (
    "SELECT text FROM document_texts WHERE text LIKE 'enc:%' LIMIT 1",
    "SELECT content FROM chat_messages WHERE content LIKE 'enc:%' LIMIT 1",
)


async def stored_fingerprint(session: AsyncSession) -> str | None:
    return await session.scalar(select(SystemState.value).where(SystemState.name == FINGERPRINT))


async def save_fingerprint(session: AsyncSession, fingerprint: str) -> None:
    statement = insert(SystemState).values(name=FINGERPRINT, value=fingerprint)
    await session.execute(
        statement.on_conflict_do_update(index_elements=[SystemState.name], set_={"value": fingerprint})
    )
    await session.commit()


async def verify_encryption_key(session: AsyncSession) -> None:
    """Raises AppError unless DATA_ENCRYPTION_KEY (or, mid-rotation,
    DATA_ENCRYPTION_KEY_PREVIOUS) is the key of the stored data."""
    current = current_fingerprint()  # also fails when the key is missing
    stored = await stored_fingerprint(session)
    if stored is None:
        # First start with a fingerprint: data from before may exist.
        for sql in _SAMPLES:
            value = await session.scalar(text(sql))
            if value is not None:
                decrypt_text(value)
        await session.execute(
            insert(SystemState)
            .values(name=FINGERPRINT, value=current)
            .on_conflict_do_nothing(index_elements=[SystemState.name])
        )
        await session.commit()
        stored = await stored_fingerprint(session)
    if stored in {current, previous_fingerprint()}:
        return
    raise AppError(
        "misconfigured",
        f"DATA_ENCRYPTION_KEY (fingerprint {current}) is not the key the stored "
        f"data is encrypted with (fingerprint {stored}). Restore the key from "
        "your backup; `uv run setup key` shows the fingerprint of a key.",
        status_code=500,
    )
