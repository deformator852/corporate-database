"""Rejects uploads whose bytes do not match their extension, and zip bombs.

Runs before the file reaches LibreOffice, MinIO, or the parsers.
"""

import io
import zipfile

from exceptions import AppError

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy .doc
_RTF = b"{\\rtf"  # Word also saves RTF as .doc
_ZIP = b"PK\x03\x04"

# Office formats are zip archives; each must contain its main part.
_ZIP_MAIN_PART = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".odt": "content.xml",
}
_TEXT_SUFFIXES = frozenset({".txt", ".csv", ".xml", ".json", ".md", ".mdx"})

# A 32 MB upload may unpack to at most this much. zipfile never reads past the
# sizes declared in the archive, so checking them bounds real decompression.
MAX_UNPACKED_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000


def _mismatch() -> AppError:
    return AppError(
        "invalid",
        "The file content does not match its type.",
        status_code=400,
    )


def check_upload(content: bytes, suffix: str) -> None:
    if suffix == ".pdf":
        # The spec allows junk before the header; readers scan the first 1 KB.
        if b"%PDF-" not in content[:1024]:
            raise _mismatch()
    elif suffix == ".doc":
        if not content.startswith((_OLE, _RTF)):
            raise _mismatch()
    elif suffix in _ZIP_MAIN_PART:
        _check_archive(content, _ZIP_MAIN_PART[suffix])
    elif suffix in _TEXT_SUFFIXES:
        if b"\x00" in content:
            raise AppError(
                "invalid",
                "The file is not plain text. Save it as UTF-8 text.",
                status_code=400,
            )


def _check_archive(content: bytes, main_part: str) -> None:
    if not content.startswith(_ZIP):
        raise _mismatch()
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, ValueError) as exc:
        raise _mismatch() from exc
    if len(entries) > MAX_ZIP_ENTRIES or (sum(entry.file_size for entry in entries) > MAX_UNPACKED_BYTES):
        raise AppError(
            "invalid",
            "The file unpacks to too much data.",
            status_code=400,
        )
    if main_part not in {entry.filename for entry in entries}:
        raise _mismatch()
