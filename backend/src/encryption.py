"""Encryption at rest for document content.

AES-256-GCM with DATA_ENCRYPTION_KEY (`uv run install` generates it), from .env
or HashiCorp Vault (key_store.py).
Encrypted: document files (on disk or in S3, services/storage.py), document
text and chats in Postgres (`EncryptedText`), chunk text in the Qdrant payload. Not encrypted: document names (the
chat matches them in SQL) and vectors (search needs them) - keep the Qdrant
and Postgres volumes on an encrypted disk for those.

Every value carries the id of the key that sealed it, so a rotation can read
old and new values side by side: DATA_ENCRYPTION_KEY_PREVIOUS holds the old
key until `python -m maintenance.rotate_key` has re-encrypted everything.

Strict: a value without the marker is an error, never read as plain text.
Otherwise anyone able to write to the database, the files or Qdrant could plant
text that users and the LLM would take for a real document.

Losing the key loses the data: back it up separately from the database.
"""

import base64
import hashlib
import hmac
import os
from functools import cache
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

import key_store
from exceptions import AppError

_TEXT_V2 = "enc:v2:"
_BYTES_V2 = b"CRPSENC2"
_NONCE_BYTES = 12
_KEY_ID_BYTES = 8
MIN_KEY_LENGTH = 32


class _Key:
    def __init__(self, secret: str) -> None:
        raw = secret.encode()
        # Any long random string works as the secret; hash it to a 256-bit key.
        self.material = hashlib.sha256(raw).digest()
        self.cipher = AESGCM(self.material)
        # Separate derivation: the id can be stored and shown without
        # revealing anything about the key itself.
        self.id = hmac.new(raw, b"corpus key id", hashlib.sha256).digest()[:_KEY_ID_BYTES]


def key_fingerprint(secret: str) -> str:
    """Printable key id, e.g. 3f9a-12c0-77be-0d41. Safe to store and show."""
    return _fingerprint(_Key(secret).id)


def _secret(name: str) -> str:
    """From .env or HashiCorp Vault, as KEY_STORE says (key_store.py)."""
    return key_store.secret(name)


@cache
def _current() -> _Key:
    secret = _secret("DATA_ENCRYPTION_KEY")
    if len(secret) < MIN_KEY_LENGTH:
        raise AppError(
            "misconfigured",
            "DATA_ENCRYPTION_KEY is not configured.",
            status_code=500,
        )
    return _Key(secret)


@cache
def _previous() -> _Key | None:
    secret = _secret("DATA_ENCRYPTION_KEY_PREVIOUS")
    if not secret:
        return None
    if len(secret) < MIN_KEY_LENGTH:
        raise AppError(
            "misconfigured",
            "DATA_ENCRYPTION_KEY_PREVIOUS is too short.",
            status_code=500,
        )
    return _Key(secret)


def reset_keys() -> None:
    """Re-reads the keys from their store (tests, rotation)."""
    key_store.forget()
    _current.cache_clear()
    _previous.cache_clear()


def current_fingerprint() -> str:
    return _fingerprint(_current().id)


def previous_fingerprint() -> str | None:
    previous = _previous()
    return None if previous is None else _fingerprint(previous.id)


def _fingerprint(key_id: bytes) -> str:
    hex_id = key_id.hex()
    return "-".join(hex_id[i : i + 4] for i in range(0, len(hex_id), 4))


def _unreadable() -> AppError:
    return AppError(
        "misconfigured",
        "Stored data cannot be decrypted with DATA_ENCRYPTION_KEY.",
        status_code=500,
    )


def _keys() -> list[_Key]:
    previous = _previous()
    return [_current()] if previous is None else [_current(), previous]


def _seal(data: bytes, context: str) -> bytes:
    key = _current()
    nonce = os.urandom(_NONCE_BYTES)
    return key.id + nonce + key.cipher.encrypt(nonce, data, context.encode())


def _open_with(key: _Key, blob: bytes, context: str) -> bytes:
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return key.cipher.decrypt(nonce, ciphertext, context.encode())


def _open(blob: bytes, context: str) -> bytes:
    key_id, rest = blob[:_KEY_ID_BYTES], blob[_KEY_ID_BYTES:]
    for key in _keys():
        if key.id == key_id:
            try:
                return _open_with(key, rest, context)
            except InvalidTag as exc:
                raise _unreadable() from exc
    raise _unreadable()


def _not_encrypted() -> AppError:
    return AppError(
        "misconfigured",
        "Stored data is not encrypted; it was not written by Corpus.",
        status_code=500,
    )


def encrypt_bytes(data: bytes, context: str = "") -> bytes:
    """`context` binds the ciphertext to its place (e.g. the object key):
    a copy moved elsewhere will not decrypt."""
    return _BYTES_V2 + _seal(data, context)


def decrypt_bytes(blob: bytes, context: str = "") -> bytes:
    if not blob.startswith(_BYTES_V2):
        raise _not_encrypted()
    return _open(blob[len(_BYTES_V2) :], context)


def is_current_bytes(blob: bytes) -> bool:
    """Sealed with the current key: nothing for a rotation to do."""
    head = len(_BYTES_V2)
    return blob.startswith(_BYTES_V2) and blob[head : head + _KEY_ID_BYTES] == _current().id


def keyed_digest(data: bytes) -> bytes:
    """A 16-byte digest keyed with the current key: equal data gives equal
    digests, but without the key nobody can test a guess against one (a
    plain hash of a short secret line can be). Digests made before a key
    rotation stop matching new ones."""
    return hmac.new(_current().material, b"corpus digest:" + data, hashlib.sha256).digest()[:16]


def encrypt_text(text: str, context: str = "") -> str:
    sealed = _seal(text.encode(), context)
    return _TEXT_V2 + base64.b64encode(sealed).decode()


def decrypt_text(value: str, context: str = "") -> str:
    if not value.startswith(_TEXT_V2):
        raise _not_encrypted()
    return _open(base64.b64decode(value[len(_TEXT_V2) :]), context).decode()


def current_text_prefix() -> str:
    """Start of every text sealed with the current key (the first 6 bytes of
    the key id are exactly 8 base64 characters), for SQL `LIKE` filters."""
    return _TEXT_V2 + base64.b64encode(_current().id[:6]).decode()


def is_current_text(value: str) -> bool:
    if not value.startswith(_TEXT_V2):
        return False
    head = base64.b64decode(value[len(_TEXT_V2) : len(_TEXT_V2) + 12])
    return head[:_KEY_ID_BYTES] == _current().id


def reencrypt_text(value: str, context: str = "") -> str:
    """`value` sealed with the current key (rotation)."""
    return value if is_current_text(value) else encrypt_text(decrypt_text(value, context), context)


def reencrypt_bytes(blob: bytes, context: str = "") -> bytes:
    return blob if is_current_bytes(blob) else encrypt_bytes(decrypt_bytes(blob, context), context)


# Streams (backups): too large for memory, so sealed in 1 MiB chunks. Each
# stream gets its own key (HKDF with a random salt), so chunk counters can
# serve as nonces. The last chunk is flagged: a truncated stream is rejected.
_STREAM_MAGIC = b"CRPSBAK1"
_STREAM_CHUNK = 1 << 20
_SALT_BYTES = 16


def _stream_cipher(key: _Key, salt: bytes) -> AESGCM:
    derived = HKDF(algorithm=SHA256(), length=32, salt=salt, info=b"corpus stream")
    return AESGCM(derived.derive(key.material))


def encrypt_stream(source: BinaryIO, target: BinaryIO) -> None:
    key = _current()
    salt = os.urandom(_SALT_BYTES)
    header = _STREAM_MAGIC + key.id + salt
    target.write(header)
    cipher = _stream_cipher(key, salt)
    index = 0
    chunk = source.read(_STREAM_CHUNK)
    while True:
        following = source.read(_STREAM_CHUNK) if chunk else b""
        final = bytes([not following])
        sealed = cipher.encrypt(index.to_bytes(12, "big"), chunk, header + final)
        target.write(final + len(sealed).to_bytes(4, "big") + sealed)
        if final == b"\x01":
            return
        chunk, index = following, index + 1


def stream_fingerprint(header: bytes) -> str:
    """Fingerprint of the key a stream was sealed with (from its header)."""
    start = len(_STREAM_MAGIC)
    return _fingerprint(header[start : start + _KEY_ID_BYTES])


def decrypt_stream(source: BinaryIO, target: BinaryIO) -> None:
    header = source.read(len(_STREAM_MAGIC) + _KEY_ID_BYTES + _SALT_BYTES)
    if len(header) < len(_STREAM_MAGIC) + _KEY_ID_BYTES + _SALT_BYTES or not header.startswith(_STREAM_MAGIC):
        raise AppError("invalid", "Not a Corpus backup file.", status_code=400)
    key_id = header[len(_STREAM_MAGIC) : len(_STREAM_MAGIC) + _KEY_ID_BYTES]
    key = next((k for k in _keys() if k.id == key_id), None)
    if key is None:
        raise AppError(
            "misconfigured",
            f"The backup was made with the key {stream_fingerprint(header)}; "
            "set it as DATA_ENCRYPTION_KEY to restore it.",
            status_code=500,
        )
    cipher = _stream_cipher(key, header[-_SALT_BYTES:])
    index = 0
    while True:
        prefix = source.read(5)
        size = int.from_bytes(prefix[1:], "big") if len(prefix) == 5 else -1
        sealed = source.read(size) if size > 0 else b""
        if size < 0 or len(sealed) != size:
            raise AppError("invalid", "The backup file is truncated.", status_code=400)
        final = prefix[:1]
        try:
            target.write(cipher.decrypt(index.to_bytes(12, "big"), sealed, header + final))
        except InvalidTag as exc:
            raise AppError("invalid", "The backup file is damaged.", status_code=400) from exc
        if final == b"\x01":
            if source.read(1):
                raise AppError("invalid", "The backup file is damaged.", status_code=400)
            return
        index += 1


class EncryptedText(TypeDecorator):
    """Text column stored encrypted; the ORM sees plain text."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        # Always sealed, even text that looks encrypted: a chat message
        # starting with "enc:v2:" is still just a chat message.
        return None if value is None else encrypt_text(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        return None if value is None else decrypt_text(value)
