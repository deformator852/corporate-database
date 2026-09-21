from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree

from docx import Document as DocxFile
from openpyxl import load_workbook
from pypdf import PdfReader

from exceptions import AppError


class TextExtractor(Protocol):
    def extract(self, content: bytes) -> str: ...


class PlainTextExtractor:
    def extract(self, content: bytes) -> str:
        return content.decode("utf-8", errors="replace")


class PdfExtractor:
    def extract(self, content: bytes) -> str:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)


class DocxExtractor:
    def extract(self, content: bytes) -> str:
        document = DocxFile(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)


class OdtExtractor:
    def extract(self, content: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("content.xml")
        root = ElementTree.fromstring(xml)
        return "\n".join(text for text in root.itertext() if text.strip())


class XlsxExtractor:
    def extract(self, content: bytes) -> str:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows: list[str] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                values = ["" if cell is None else str(cell) for cell in row]
                if any(value.strip() for value in values):
                    rows.append("\t".join(values))
        return "\n".join(rows)


class CsvExtractor:
    def extract(self, content: bytes) -> str:
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        return "\n".join("\t".join(row) for row in reader)


class XmlExtractor:
    def extract(self, content: bytes) -> str:
        root = ElementTree.fromstring(content)
        return "\n".join(text for text in root.itertext() if text.strip())


class JsonExtractor:
    def extract(self, content: bytes) -> str:
        payload = json.loads(content.decode("utf-8"))
        return json.dumps(payload, ensure_ascii=False, indent=2)


class DocumentParser:
    def __init__(self) -> None:
        plain = PlainTextExtractor()
        self._extractors: dict[str, TextExtractor] = {
            ".txt": plain,
            ".md": plain,
            ".mdx": plain,
            ".pdf": PdfExtractor(),
            ".docx": DocxExtractor(),
            ".odt": OdtExtractor(),
            ".xlsx": XlsxExtractor(),
            ".csv": CsvExtractor(),
            ".xml": XmlExtractor(),
            ".json": JsonExtractor(),
        }

    def parse(self, content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        extractor = self._extractors.get(suffix)
        if extractor is None:
            raise AppError(
                "invalid",
                "This file type is not supported.",
                status_code=400,
            )
        try:
            text = extractor.extract(content)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "invalid",
                "Could not read the document.",
                status_code=400,
            ) from exc
        if not text.strip():
            raise AppError(
                "invalid",
                "The document has no text.",
                status_code=400,
            )
        return text
