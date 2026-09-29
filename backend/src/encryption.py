"""Encryption at rest for document content.

AES-256-GCM with DATA_ENCRYPTION_KEY from .env (`uv run setup` generates it).
Encrypted: files in MinIO, document text in Postgres (`EncryptedText`), chunk
text in the Qdrant payload, chat messages. Not encrypted: document names (the
chat matches them in SQL) and vectors (search needs them) - keep the Qdrant
and Postgres volumes on an encrypted disk for those.

Values written before encryption was enabled have no marker and are read as
they are; `python -m maintenance.encrypt_existing` converts them.

Losing the key loses the data: back it up separately from the database.
"""

import base64
import hashlib
import os
from functools import cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from exceptions import AppError

# Version markers leave room for key rotation (v2 with a new key).
_TEXT_PREFIX = "enc:v1:"
_BYTES_MAGIC = b"CRPSENC1"
_NONCE_BYTES = 12


@cache
def _cipher() -> AESGCM:
    secret = (os.getenv("DATA_ENCRYPTION_KEY") or "").strip()
    if len(secret) < 32:
        raise AppError(
            "misconfigured",
            "DATA_ENCRYPTION_KEY is not configured.",
            status_code=500,
        )
    # Any long random string works as the secret; hash it to a 256-bit key.
    return AESGCM(hashlib.sha256(secret.encode()).digest())


def _seal(data: bytes, context: str) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + _cipher().encrypt(nonce, data, context.encode())


def _open(blob: bytes, context: str) -> bytes:
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        return _cipher().decrypt(nonce, ciphertext, context.encode())
    except InvalidTag as exc:
        raise AppError(
            "misconfigured",
            "Stored data cannot be decrypted with DATA_ENCRYPTION_KEY.",
            status_code=500,
        ) from exc


def encrypt_bytes(data: bytes, context: str = "") -> bytes:
    """`context` binds the ciphertext to its place (e.g. the object key):
    a copy moved elsewhere will not decrypt."""
    return _BYTES_MAGIC + _seal(data, context)


def decrypt_bytes(blob: bytes, context: str = "") -> bytes:
    if not blob.startswith(_BYTES_MAGIC):
        return blob  # stored before encryption was enabled
    return _open(blob[len(_BYTES_MAGIC) :], context)


def is_encrypted_bytes(blob: bytes) -> bool:
    return blob.startswith(_BYTES_MAGIC)


def encrypt_text(text: str, context: str = "") -> str:
    sealed = _seal(text.encode(), context)
    return _TEXT_PREFIX + base64.b64encode(sealed).decode()


def decrypt_text(value: str, context: str = "") -> str:
    if not value.startswith(_TEXT_PREFIX):
        return value  # stored before encryption was enabled
    return _open(base64.b64decode(value[len(_TEXT_PREFIX) :]), context).decode()


def is_encrypted_text(value: str) -> bool:
    return value.startswith(_TEXT_PREFIX)


class EncryptedText(TypeDecorator):
    """Text column stored encrypted; the ORM sees plain text."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None or is_encrypted_text(value):
            return value
        return encrypt_text(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        return None if value is None else decrypt_text(value)
