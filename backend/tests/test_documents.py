"""Uploads are checked; files open only for users allowed to read them."""

import io
import zipfile

import pytest

from conftest import login, run
from exceptions import AppError
from services.documents.upload_check import check_upload


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("content", "suffix"),
    [
        (b"%PDF-1.7\n...", ".pdf"),
        (_zip({"word/document.xml": b"<w/>"}), ".docx"),
        (_zip({"xl/workbook.xml": b"<x/>"}), ".xlsx"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 64, ".doc"),
        ("Привіт".encode(), ".txt"),
    ],
)
def test_real_files_pass(content, suffix):
    check_upload(content, suffix)


@pytest.mark.parametrize(
    ("content", "suffix"),
    [
        (b"MZ\x90\x00" + b"\0" * 64, ".pdf"),
        (_zip({"xl/workbook.xml": b"<x/>"}), ".docx"),
        (b"abc\x00\x01", ".txt"),
        (_zip({"word/document.xml": b"<w/>", "big": b"\0" * (300 * 1024 * 1024)}), ".docx"),
    ],
)
def test_disguised_or_bomb_files_are_rejected(content, suffix):
    with pytest.raises(AppError):
        check_upload(content, suffix)


class _MemoryStorage:
    files: dict[str, bytes] = {}

    def get(self, key: str) -> bytes:
        return self.files[key]


def _document(classification: str) -> int:
    from database import AsyncSessionLocal
    from models import Document, User
    from sqlalchemy import select

    async def create() -> int:
        async with AsyncSessionLocal() as session:
            owner = await session.scalar(select(User.id).limit(1))
            doc = Document(
                name=f"Doc {classification}",
                filename="doc.txt",
                content_type="text/plain",
                size=5,
                status="completed",
                progress=100,
                object_key=f"documents/{classification}",
                classification=classification,
                user_id=owner,
            )
            session.add(doc)
            await session.commit()
            return doc.id

    _MemoryStorage.files[f"documents/{classification}"] = b"hello"
    return run(create())


def test_file_opens_only_within_clearance(client, make_user):
    import main
    from api.deps import get_storage

    main.app.dependency_overrides[get_storage] = _MemoryStorage
    try:
        _, email, password = make_user(["documents.list"])
        standard, secret = _document("standard"), _document("secret")
        login(client, email, password)
        response = client.get(f"/api/v1/documents/{standard}/file")
        assert response.status_code == 200 and response.content == b"hello"
        assert "sandbox" in response.headers["content-security-policy"]
        # Forbidden looks like missing: nothing about its existence leaks.
        assert client.get(f"/api/v1/documents/{secret}/file").status_code == 404
        views = client.get("/api/v1/audit", params={"action": "documents.view"})
        assert views.status_code == 403  # plain users cannot read the audit log
    finally:
        main.app.dependency_overrides.clear()
