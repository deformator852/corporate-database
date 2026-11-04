"""Encryption at rest."""

import os

import pytest
from conftest import run
from sqlalchemy import text

import encryption
from encryption import (
    current_fingerprint,
    decrypt_bytes,
    decrypt_text,
    encrypt_bytes,
    encrypt_text,
    is_current_text,
    reencrypt_text,
)
from exceptions import AppError

OLD_KEY = os.environ["DATA_ENCRYPTION_KEY"]
NEW_KEY = "rotated-encryption-key-" + "n" * 32


@pytest.fixture
def keys():
    """Sets DATA_ENCRYPTION_KEY(_PREVIOUS) for one test, then restores them."""

    def use(current: str, previous: str | None = None) -> None:
        os.environ["DATA_ENCRYPTION_KEY"] = current
        if previous is None:
            os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)
        else:
            os.environ["DATA_ENCRYPTION_KEY_PREVIOUS"] = previous
        encryption.reset_keys()

    yield use
    use(OLD_KEY)


def test_roundtrip_and_random_nonce():
    assert decrypt_text(encrypt_text("Сумма 125 000", "a"), "a") == "Сумма 125 000"
    assert encrypt_text("x") != encrypt_text("x")
    assert decrypt_bytes(encrypt_bytes(b"file", "k"), "k") == b"file"


def test_ciphertext_is_bound_to_its_place():
    with pytest.raises(AppError):
        decrypt_bytes(encrypt_bytes(b"file", "documents/a"), "documents/b")


def test_unencrypted_values_are_rejected():
    # Planted plain text must not reach users or the LLM as a document.
    with pytest.raises(AppError, match="not encrypted"):
        decrypt_text("plain")
    with pytest.raises(AppError, match="not encrypted"):
        decrypt_bytes(b"%PDF-1.7")


def test_text_that_looks_encrypted_is_still_encrypted():
    from encryption import EncryptedText

    planted = encrypt_text("forged")
    stored = EncryptedText().process_bind_param(planted, None)
    assert stored != planted and decrypt_text(stored) == planted


def test_document_text_is_stored_encrypted():
    from sqlalchemy import select

    from database import AsyncSessionLocal
    from models import Document, DocumentText, User

    async def scenario() -> tuple[str, str]:
        async with AsyncSessionLocal() as session:
            owner = await session.scalar(select(User.id).limit(1))
            doc = Document(
                name="Enc",
                filename="e.txt",
                content_type="text/plain",
                size=1,
                status="completed",
                progress=100,
                object_key="k",
                classification="standard",
                user_id=owner,
            )
            session.add(doc)
            await session.flush()
            session.add(DocumentText(document_id=doc.id, text="secret salary table"))
            await session.commit()
            raw = await session.scalar(text("SELECT text FROM document_texts WHERE document_id = :i"), {"i": doc.id})
            loaded = await session.scalar(select(DocumentText.text).where(DocumentText.document_id == doc.id))
            return raw, loaded

    raw, loaded = run(scenario())
    assert raw.startswith("enc:v2:") and "salary" not in raw
    assert loaded == "secret salary table"


def test_rotation_reads_both_keys_and_writes_the_new_one(keys):
    old = encrypt_text("before", "c")
    keys(NEW_KEY, previous=OLD_KEY)
    assert not is_current_text(old)
    assert decrypt_text(old, "c") == "before"
    fresh = encrypt_text("after", "c")
    assert is_current_text(fresh)
    assert decrypt_text(reencrypt_text(old, "c"), "c") == "before"
    keys(NEW_KEY)  # rotation finished: the old key is gone
    with pytest.raises(AppError):
        decrypt_text(old, "c")
    assert decrypt_text(fresh, "c") == "after"


def test_the_key_can_come_from_vault_and_never_from_env(monkeypatch):
    from fakes import FakeVault

    import key_store
    from encryption import key_fingerprint

    fake = FakeVault()
    key = "key-held-in-vault-" + "v" * 32
    fake.secrets["archfold"] = {"DATA_ENCRYPTION_KEY": key}

    class Bound(key_store.VaultClient):
        def __init__(self, config, transport=None):
            super().__init__(config, fake.transport())

    monkeypatch.setattr(key_store, "VaultClient", Bound)
    monkeypatch.setenv("KEY_STORE", "vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.test:8200")
    monkeypatch.setenv("VAULT_ROLE_ID", "archfold-role")
    monkeypatch.setenv("VAULT_SECRET_ID", "archfold-secret")
    monkeypatch.setenv("VAULT_CONNECT", "vault-tunnel:8200")  # as in production
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "an-env-key-that-must-be-ignored-" + "e" * 16)
    try:
        encryption.reset_keys()
        assert current_fingerprint() == key_fingerprint(key)
        assert decrypt_text(encrypt_text("salary list")) == "salary list"
        # Through the tunnel, but to Vault: its Host header and TLS name.
        assert fake.last.url.host == "vault-tunnel"
        assert fake.last.headers["host"] == "vault.test:8200"
        assert fake.last.extensions["sni_hostname"] == "vault.test"
        assert [path for _, path, _ in fake.requests] == ["auth/approle/login", "secret/data/archfold"]  # once

        monkeypatch.setenv("VAULT_SECRET_ID", "revoked")
        encryption.reset_keys()
        with pytest.raises(AppError, match="invalid role"):
            current_fingerprint()
    finally:
        monkeypatch.setenv("KEY_STORE", "env")
        monkeypatch.delenv("DATA_ENCRYPTION_KEY")
        monkeypatch.undo()
        encryption.reset_keys()  # back to the test key from the environment


def test_fingerprint_does_not_reveal_the_key():
    fingerprint = current_fingerprint()
    assert len(fingerprint) == 19 and OLD_KEY not in fingerprint
    assert fingerprint == encryption.key_fingerprint(OLD_KEY)
    assert fingerprint != encryption.key_fingerprint(NEW_KEY)


def test_startup_refuses_another_key(keys):
    from database import AsyncSessionLocal
    from services.encryption_key import stored_fingerprint, verify_encryption_key

    async def verify() -> None:
        async with AsyncSessionLocal() as session:
            await verify_encryption_key(session)

    async def stored() -> str | None:
        async with AsyncSessionLocal() as session:
            return await stored_fingerprint(session)

    run(verify())  # records the fingerprint on first start
    assert run(stored()) == current_fingerprint()
    keys("some-other-key-" + "w" * 32)
    with pytest.raises(AppError, match="not the key"):
        run(verify())
    keys(NEW_KEY, previous=OLD_KEY)  # mid-rotation is fine
    run(verify())


def test_rotate_key_reencrypts_the_database(keys, make_user):
    from sqlalchemy import select

    from database import AsyncSessionLocal
    from maintenance.rotate_key import _column, encrypted_columns
    from models import ChatConversation, ChatMessageRecord, ErrorLog
    from services.encryption_key import save_fingerprint

    owner, _, _ = make_user()

    async def seed() -> int:
        async with AsyncSessionLocal() as session:
            await save_fingerprint(session, current_fingerprint())
            chat = ChatConversation(user_id=owner, title="Payroll question")
            session.add(chat)
            await session.flush()
            session.add(ChatMessageRecord(conversation_id=chat.id, role="user", content="Who earns most?"))
            session.add(ErrorLog(level="error", source="backend", logger="test", message="Payroll failed"))
            await session.commit()
            return chat.id

    async def rotate() -> None:
        for table, key, column in encrypted_columns():
            await _column(table, key, column)

    # Every encrypted column, the error log too: unreadable after the old key goes.
    assert {(t, c) for t, _, c in encrypted_columns()} >= {
        ("document_texts", "text"),
        ("chat_conversations", "title"),
        ("chat_messages", "content"),
        ("error_logs", "message"),
        ("error_logs", "traceback"),
    }

    async def read(chat_id: int) -> tuple[str, str, str]:
        async with AsyncSessionLocal() as session:
            raw = await session.scalar(
                text("SELECT content FROM chat_messages WHERE conversation_id = :i"), {"i": chat_id}
            )
            title = await session.scalar(select(ChatConversation.title).where(ChatConversation.id == chat_id))
            content = await session.scalar(
                select(ChatMessageRecord.content).where(ChatMessageRecord.conversation_id == chat_id)
            )
            return raw, title, content

    chat_id = run(seed())
    keys(NEW_KEY, previous=OLD_KEY)
    run(rotate())
    keys(NEW_KEY)
    raw, title, content = run(read(chat_id))
    assert is_current_text(raw)
    assert (title, content) == ("Payroll question", "Who earns most?")

    async def error_messages() -> list[str]:
        async with AsyncSessionLocal() as session:
            return list(await session.scalars(select(ErrorLog.message).where(ErrorLog.logger == "test")))

    assert run(error_messages()) == ["Payroll failed"]
    # Back to the old key: other tests read rows this rotation sealed.
    keys(OLD_KEY, previous=NEW_KEY)
    run(rotate())
    run(rotate())  # nothing left: a second run is a no-op


def test_backup_stream_roundtrip_and_tamper_detection(keys):
    import io

    from encryption import decrypt_stream, encrypt_stream

    def seal(data: bytes) -> bytes:
        out = io.BytesIO()
        encrypt_stream(io.BytesIO(data), out)
        return out.getvalue()

    def unseal(blob: bytes) -> bytes:
        out = io.BytesIO()
        decrypt_stream(io.BytesIO(blob), out)
        return out.getvalue()

    big = os.urandom((1 << 20) * 2 + 123)  # three chunks
    for data in (b"", b"pg_dump", big):
        assert unseal(seal(data)) == data
    blob = seal(big)
    assert b"pg_dump" not in seal(b"pg_dump")
    with pytest.raises(AppError, match="truncated|damaged"):
        unseal(blob[: len(blob) // 2])  # cut at a chunk boundary or inside
    first_chunk_end = 32 + 5 + (1 << 20) + 16
    with pytest.raises(AppError, match="truncated"):
        unseal(blob[:first_chunk_end])  # whole chunks, final one missing
    flipped = bytearray(blob)
    flipped[100] ^= 1
    with pytest.raises(AppError, match="damaged"):
        unseal(bytes(flipped))
    keys(NEW_KEY)
    with pytest.raises(AppError, match="made with the key"):
        unseal(blob)
