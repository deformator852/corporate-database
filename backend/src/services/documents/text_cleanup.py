"""Text cleanup before embedding, by rules: what a pattern finds reliably -
control and zero-width characters, broken encodings, hyphenated line breaks,
dot leaders, decorative separators, repeated headers/footers, page numbers.

An LLM rewrite was measured with evals/text_cleanup.py and removed: no steady
gain in search over these rules, at 10-25 s per chunk.

Only the embedded text is cleaned. Answers and search results carry the
original text (`document_texts`, the Qdrant payload), so cleanup never
changes what users and the assistant read.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Callable

_INVISIBLE = re.compile(r"[­​-‏  ⁠﻿�]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# "infor-\nmation" -> "information" (letters on both sides only)
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
# Table-of-contents leaders: "Introduction ........ 5"
_DOT_LEADER = re.compile(r"(?:\s?[.·_-]){4,}\s?")
# Lines made only of decoration: "*****", "=====", "-----", "• • •"
_DECORATION_LINE = re.compile(r"^[\s*=_~#•●▪►◆■□✓✔→\-–—|+.]{3,}$")
_PAGE_NUMBER_LINE = re.compile(
    r"^(?:(?:page|p\.|стор\.?|страница|стр\.?|página|sayfa)\s*)?"
    # Up to 3 digits: a year alone on a line ("2025") is not a page number.
    r"[-–—]?\s*\d{1,3}\s*(?:(?:/|of|из|з|de|sur)\s*\d{1,4})?\s*[-–—]?$",
    re.IGNORECASE,
)
_SPACES = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
# A short line repeated this often is a running header/footer.
_REPEATED_LINE_MIN = 3
_REPEATED_LINE_MAX_LENGTH = 80
# Lines checked at the top and at the bottom of every page.
_EDGE_LINES = 2
_DIGITS = re.compile(r"\d+")


def normalized_lines(text: str) -> list[str]:
    """Lines as the rules see them: normalized characters and spaces."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", _CONTROL.sub("", text))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    return [_SPACES.sub(" ", _DOT_LEADER.sub(" ", line)).strip() for line in text.split("\n")]


def repeated_lines(text: str) -> frozenset[str]:
    """Short lines found often enough in the whole document to be running
    headers or footers."""
    counts = Counter(line for line in normalized_lines(text) if line and len(line) <= _REPEATED_LINE_MAX_LENGTH)
    return frozenset(line for line, count in counts.items() if count >= _REPEATED_LINE_MIN)


def _shape(line: str) -> str:
    """The line with numbers masked: "Page 3 of 9" and "Page 4 of 9" match."""
    return _DIGITS.sub("#", line)


def page_edge_lines(pages: list[str]) -> frozenset[str]:
    """Shapes of the lines at the top or bottom of at least half the pages:
    running headers, footers and page numbers. Only page edges count, so a
    value repeated inside tables or text is never taken for one."""
    counts: Counter[str] = Counter()
    for page in pages:
        lines = [line for line in normalized_lines(page) if line]
        counts.update({_shape(line) for line in lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]})
    needed = max(_REPEATED_LINE_MIN, len(pages) // 2)
    return frozenset(shape for shape, count in counts.items() if count >= needed)


def furniture_of(document: str) -> Callable[[str], bool]:
    """Which lines of `document` are page furniture; its chunks are cleaned
    with it. A paged document (PDF, pages split by PAGE_BREAK): lines at the
    page edges. Otherwise there are no pages to go by: short lines repeated
    3+ times and lines that look like page numbers."""
    pages = document.split("\f")
    if len(pages) >= _REPEATED_LINE_MIN:
        edges = page_edge_lines(pages)
        return lambda line: _shape(line) in edges
    repeated = repeated_lines(document)
    return lambda line: line in repeated or bool(_PAGE_NUMBER_LINE.match(line))


def basic_clean(
    text: str,
    *,
    structured: bool = False,
    furniture: Callable[[str], bool] | None = None,
) -> str:
    """Rules-only cleanup. `structured` (CSV, JSON, XML, spreadsheets): only
    character-level fixes; a line holding "12" or a repeated row is data there.
    `furniture`: the whole document's (furniture_of), when `text` is one of
    its chunks."""
    if structured:
        text = unicodedata.normalize("NFKC", text)
        text = _INVISIBLE.sub("", _CONTROL.sub("", text))
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if furniture is None:
        furniture = furniture_of(text)
    kept = [line for line in normalized_lines(text) if not _DECORATION_LINE.match(line) and not furniture(line)]
    return _BLANK_LINES.sub("\n\n", "\n".join(kept)).strip()
