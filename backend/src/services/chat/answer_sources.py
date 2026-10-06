"""Which documents an answer used. The model ends an answer built on
documents with a SOURCES line (SOURCES_RULE); it is cut from the text and
from the stream, and each document it names must also show in the answer,
since small models tend to name every document they were given. Search alone
cannot tell: a second hit scores alike whether the answer needs it or not.
"""

import re
from collections.abc import Awaitable, Callable, Sequence

from services.chat.context_document import ContextDocument

OnDelta = Callable[[str], Awaitable[None]]

SOURCES_RULE = (
    "After the answer, write one last line that starts with SOURCES: and lists "
    "only the documents your answer took facts from, separated by semicolons. "
    "Leave out every document you did not take a fact from. If no document "
    "answers the question, write SOURCES: none."
)
_SOURCES_LINE = re.compile(r"^[\W_]*sources[\W_]*:(.*)$", re.IGNORECASE)
# A source must also show in the answer: share of the answer's own words
# (not taken from the question) found in the document. Measured with
# evals/chat_sources.py: sources score 0.22-1.0, other documents mostly 0.
# Small models tend to name every document they were given.
_MIN_SUPPORT = 0.2
_WORD = re.compile(r"\w+")


class HideSourcesLine:
    """Streams the answer on, except the closing sources line. A line is held
    back only while it could still turn into that line."""

    def __init__(self, on_delta: OnDelta | None) -> None:
        self.on_delta = on_delta
        self.line = ""
        self.hidden = False

    async def feed(self, piece: str) -> None:
        if self.hidden:
            return
        self.line += piece
        while "\n" in self.line and not self.hidden:
            line, self.line = self.line.split("\n", 1)
            if _SOURCES_LINE.match(line):
                self.hidden = True
                return
            await self._emit(line + "\n")
        if not self.hidden and not _could_be_sources(self.line):
            await self._emit(self.line)
            self.line = ""

    async def flush(self) -> None:
        if not self.hidden and self.line and not _SOURCES_LINE.match(self.line):
            await self._emit(self.line)
        self.line = ""

    async def _emit(self, text: str) -> None:
        if text and self.on_delta is not None:
            await self.on_delta(text)


def _could_be_sources(line: str) -> bool:
    letters = re.sub(r"[\W_]", "", line).lower()
    return bool(_SOURCES_LINE.match(line)) or (len(letters) <= len("sources") and "sources".startswith(letters))


def _split_sources(text: str, documents: Sequence[ContextDocument]) -> tuple[str, list[ContextDocument]]:
    """The answer without its sources line, and the documents that line names."""
    lines = text.rstrip().split("\n")
    for index in range(len(lines) - 1, -1, -1):
        match = _SOURCES_LINE.match(lines[index].strip())
        if match:
            named = match.group(1).lower()
            used = [d for d in documents if _named(d, named)]
            return "\n".join(lines[:index]).strip(), used
    return text.strip(), list(documents)


def _words(text: str) -> set[str]:
    """Words that can carry a fact: numbers and words of five letters or
    more. Short ones ("does", "with", "pour") belong to the language."""
    return {w.lower() for w in _WORD.findall(text) if len(w) >= 5 or w.isdigit()}


def support(answer: str, question: str, document: ContextDocument) -> float:
    """Share of the answer's own words (beyond the question) in `document`."""
    # An answer that only repeats the question ("No, alcohol is not paid
    # back") is judged by all its words.
    own = (_words(answer) - _words(question)) or _words(answer)
    if not own:
        return 0.0
    return len(own & _words(document.text)) / len(own)


def _supported(answer: str, question: str, documents: Sequence[ContextDocument]) -> list[ContextDocument]:
    """Documents the answer draws on. No comparison between documents: a
    two-part answer may take only a little from its second document."""
    return [d for d in documents if support(answer, question, d) >= _MIN_SUPPORT]


def _named(document: ContextDocument, sources: str) -> bool:
    return any(name and name.lower() in sources for name in (document.filename, document.name))


def sources_of(text: str, question: str, documents: Sequence[ContextDocument]) -> tuple[str, list[ContextDocument]]:
    """The answer without its sources line, and the documents it used: named
    in that line (every document when the line is missing) and holding facts
    of the answer."""
    content, named = _split_sources(text, documents)
    return content, _supported(content, question, named)
