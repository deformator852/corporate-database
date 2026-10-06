from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree

import pdfplumber
from docx import Document as DocxFile
from docx.table import Table
from openpyxl import load_workbook
from pypdf import PdfReader

from exceptions import AppError


class TextExtractor(Protocol):
    def extract(self, content: bytes) -> str: ...


class PlainTextExtractor:
    def extract(self, content: bytes) -> str:
        return content.decode("utf-8", errors="replace")


# Between pages of a PDF: cleanup finds running headers and footers by
# where lines sit on the pages (text_cleanup.page_edge_lines).
PAGE_BREAK = "\n\f\n"


class PdfExtractor:
    """Pages with ruled tables are read by pdfplumber, which keeps a table row
    on one line ("Engineering\t120\t$5,000,000"); pypdf gives one cell per
    line, losing which value belongs to which row. Other pages keep pypdf: it
    reads multi-column text column by column, where pdfplumber interleaves
    the columns line by line."""

    def extract(self, content: bytes) -> str:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for index, page in enumerate(pdf.pages):
                tables = page.find_tables()
                if tables and index < len(pages):
                    pages[index] = _page_with_tables(page, tables)
        return PAGE_BREAK.join(pages)


def _page_with_tables(page, tables) -> str:
    """The page's text and tables in reading order, top to bottom."""
    boxes = [table.bbox for table in tables]

    def outside_tables(obj: dict) -> bool:
        if "x0" not in obj or "top" not in obj:
            return True
        x = (obj["x0"] + obj["x1"]) / 2
        y = (obj["top"] + obj["bottom"]) / 2
        return not any(x0 <= x <= x1 and top <= y <= bottom for x0, top, x1, bottom in boxes)

    text = page.filter(outside_tables)
    left, top, right, bottom = page.bbox
    parts: list[str] = []
    for table in sorted(tables, key=lambda table: table.bbox[1]):
        # Text above the table and beside it.
        parts.append(text.crop((left, top, right, min(table.bbox[3], bottom))).extract_text() or "")
        parts += ["\t".join((cell or "").replace("\n", " ").strip() for cell in row) for row in table.extract()]
        top = min(max(top, table.bbox[3]), bottom)
    parts.append(text.crop((left, top, right, bottom)).extract_text() or "")
    return "\n".join(part for part in parts if part.strip())


class DocxExtractor:
    def extract(self, content: bytes) -> str:
        document = DocxFile(io.BytesIO(content))
        lines: list[str] = []
        # Paragraphs and tables in document order; a table row is one line.
        # Headings become Markdown ("## Hotels"): chunks are cut at sections
        # (processor._split_text), and the chat sees the structure.
        for block in document.iter_inner_content():
            if isinstance(block, Table):
                lines += ["\t".join(cell.text for cell in row.cells) for row in block.rows]
            else:
                lines.append(_heading(_docx_heading_level(block), block.text))
        return "\n".join(lines)


def _docx_heading_level(paragraph) -> int:
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return 1
    level = style.removeprefix("Heading ")
    return int(level) if level != style and level.isdigit() else 0


def _heading(level: int, text: str) -> str:
    if level < 1 or not text.strip():
        return text
    return f"{'#' * min(level, 6)} {text.strip()}"


_ODT_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_ODT_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"


class OdtExtractor:
    """One line per paragraph, headings as Markdown, a table row per line."""

    def extract(self, content: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("content.xml")
        lines = list(_odt_lines(ElementTree.fromstring(xml)))
        return "\n".join(line for line in lines if line.strip())


def _odt_lines(element):
    if element.tag == f"{_ODT_TEXT}h":
        level = element.get(f"{_ODT_TEXT}outline-level") or "1"
        yield _heading(int(level) if level.isdigit() else 1, _odt_text(element))
    elif element.tag == f"{_ODT_TEXT}p":
        yield _odt_text(element)
    elif element.tag == f"{_ODT_TABLE}table-row":
        yield "\t".join(
            " ".join(_odt_text(paragraph) for paragraph in cell).strip()
            for cell in element
            if cell.tag == f"{_ODT_TABLE}table-cell"
        )
    else:
        for child in element:
            yield from _odt_lines(child)


def _odt_text(element) -> str:
    """Text of a paragraph with its spans; <text:s/> is spaces, not nothing."""
    parts = [element.text or ""]
    for child in element:
        if child.tag == f"{_ODT_TEXT}s":
            parts.append(" " * int(child.get(f"{_ODT_TEXT}c") or 1))
        elif child.tag == f"{_ODT_TEXT}tab":
            parts.append("\t")
        elif child.tag == f"{_ODT_TEXT}line-break":
            parts.append(" ")
        else:
            parts.append(_odt_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


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
