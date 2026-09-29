"""Encryption at rest."""

import pytest
from sqlalchemy import text

from conftest import run
from encryption import decrypt_bytes, decrypt_text, encrypt_bytes, encrypt_text
from exceptions import AppError


def test_roundtrip_and_random_nonce():
    assert decrypt_text(encrypt_text("Сумма 125 000", "a"), "a") == "Сумма 125 000"
    assert encrypt_text("x") != encrypt_text("x")
    assert decrypt_bytes(encrypt_bytes(b"file", "k"), "k") == b"file"


def test_ciphertext_is_bound_to_its_place():
    with pytest.raises(AppError):
        decrypt_bytes(encrypt_bytes(b"file", "documents/a"), "documents/b")


def test_data_from_before_encryption_still_reads():
    assert decrypt_text("plain") == "plain"
    assert decrypt_bytes(b"%PDF-1.7") == b"%PDF-1.7"


def test_document_text_is_stored_encrypted():
    from database import AsyncSessionLocal
    from models import Document, DocumentText, User
    from sqlalchemy import select

    async def scenario() -> tuple[str, str]:
        async with AsyncSessionLocal() as session:
            owner = await session.scalar(select(User.id).limit(1))
            doc = Document(name="Enc", filename="e.txt", content_type="text/plain", size=1, status="completed", progress=100, object_key="k", classification="standard", user_id=owner)
            session.add(doc)
            await session.flush()
            session.add(DocumentText(document_id=doc.id, text="secret salary table"))
            await session.commit()
            raw = await session.scalar(text("SELECT text FROM document_texts WHERE document_id = :i"), {"i": doc.id})
            loaded = await session.scalar(select(DocumentText.text).where(DocumentText.document_id == doc.id))
            return raw, loaded

    raw, loaded = run(scenario())
    assert raw.startswith("enc:v1:") and "salary" not in raw
    assert loaded == "secret salary table"
