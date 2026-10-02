import re
from collections.abc import Awaitable, Callable, Sequence

import httpx
from ollama import AsyncClient, RequestError, ResponseError

from exceptions import AppError
from schemas.chat import ChatMessageSchema
from settings import LANGUAGES, language, llm_host, llm_model, llm_num_ctx

_TIMEOUT = httpx.Timeout(180.0)

_SYSTEM = (
    "You are a read-only assistant for this workspace. You cannot create, "
    "change, delete, or add any data anywhere. You have no tools and no "
    "ability to modify files, documents, users, roles, or any other records. "
    "Provide information only about the documents in the user message. Do not "
    "answer questions that are not about those documents. If the documents "
    "are missing or do not contain the answer, say you do not have relevant "
    "documents. Always reply in {language}, whatever the language of the "
    "question or documents. If the user asked for the full document, "
    "reproduce it completely as written. Otherwise answer concisely. Do not "
    "invent sources, and do not cite documents by name or number: the "
    "interface lists the sources under your answer."
)


OnDelta = Callable[[str], Awaitable[None]]
Document = dict[str, object]

# The model ends an answer built on documents with this line; it is cut from
# the text and tells which documents were really used (search alone cannot:
# a second hit scores alike whether the answer needs it or not).
_SOURCES_RULE = (
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

# Rough chars per token for budgeting (Latin ~4, Cyrillic ~2.5).
_CHARS_PER_TOKEN = 3
# Room for the system prompt, the sources rule and the prompt labels.
_PROMPT_OVERHEAD_TOKENS = 512


def _documents_tokens(num_ctx: int) -> int:
    """A quarter of the context is the answer, a quarter the chat history
    (with the question); documents get the rest."""
    return num_ctx - num_ctx // 4 - num_ctx // 4 - _PROMPT_OVERHEAD_TOKENS


def document_budget_chars(documents: int) -> int:
    """Characters of document text one of `documents` documents may take in
    the prompt; longer ones are sent as excerpts (services/chat.py)."""
    budget = _documents_tokens(llm_num_ctx()) * _CHARS_PER_TOKEN
    return budget // max(documents, 1)


class OllamaGenerator:
    def __init__(self, client: AsyncClient | None = None) -> None:
        self.client = client or AsyncClient(host=llm_host(), timeout=_TIMEOUT)

    async def warm_up(self) -> None:
        """Loads the model with the same num_ctx chat uses, so the first
        question does not wait for it."""
        await self.client.generate(
            model=llm_model(), prompt="", options={"num_ctx": llm_num_ctx()}
        )

    async def complete(
        self,
        messages: Sequence[ChatMessageSchema],
        documents: Sequence[Document],
        on_delta: OnDelta | None = None,
    ) -> tuple[str, list[Document]]:
        """The answer and the documents it used: named in the model's sources
        line (every document when the line is missing) and holding facts of
        the answer. Each piece of the answer also goes to `on_delta` as it is
        generated, without the sources line."""
        num_ctx = llm_num_ctx()
        num_predict = num_ctx // 4
        payload = [
            {
                "role": "system",
                "content": _SYSTEM.format(language=LANGUAGES[language()]),
            },
            *_history(messages, num_ctx // 4 * _CHARS_PER_TOKEN),
        ]
        budget = _documents_tokens(num_ctx) * _CHARS_PER_TOKEN
        context = _context(documents, budget)
        if context:
            payload[-1]["content"] = (
                f"Documents:\n{context}\n\nQuestion:\n{payload[-1]['content']}"
                f"\n\n{_SOURCES_RULE}"
            )
        parts: list[str] = []
        stream_out = _HideSourcesLine(on_delta)
        try:
            stream = await self.client.chat(
                model=llm_model(),
                messages=payload,
                think=False,
                stream=True,
                options={
                    "temperature": 0.2,
                    "num_predict": num_predict,
                    "num_ctx": num_ctx,
                },
            )
            async for chunk in stream:
                piece = chunk.message.content or ""
                if not piece:
                    continue
                parts.append(piece)
                await stream_out.feed(piece)
        except ResponseError as exc:
            if exc.status_code == 404:
                raise AppError(
                    "unavailable",
                    "The chat model is not available.",
                    status_code=503,
                ) from exc
            raise AppError(
                "unavailable",
                "The chat model failed.",
                status_code=503,
            ) from exc
        except (RequestError, httpx.RequestError, httpx.HTTPError) as exc:
            raise AppError(
                "unavailable",
                "Could not reach the chat model.",
                status_code=503,
            ) from exc
        await stream_out.flush()
        content, used = _split_sources("".join(parts), documents if context else [])
        used = _supported(content, messages[-1].content, used)
        if not content:
            raise AppError(
                "unavailable",
                "The chat model returned an empty answer.",
                status_code=503,
            )
        return content, used


class _HideSourcesLine:
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


def _split_sources(text: str, documents: Sequence[Document]) -> tuple[str, list[Document]]:
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


def _support(answer: str, question: str, document: Document) -> float:
    """Share of the answer's own words (beyond the question) in `document`."""
    # An answer that only repeats the question ("No, alcohol is not paid
    # back") is judged by all its words.
    own = (_words(answer) - _words(question)) or _words(answer)
    if not own:
        return 0.0
    return len(own & _words(str(document.get("text") or ""))) / len(own)


def _supported(answer: str, question: str, documents: Sequence[Document]) -> list[Document]:
    """Documents the answer draws on. No comparison between documents: a
    two-part answer may take only a little from its second document."""
    return [d for d in documents if _support(answer, question, d) >= _MIN_SUPPORT]


def _named(document: Document, sources: str) -> bool:
    names = (str(document.get("filename") or ""), str(document.get("name") or ""))
    return any(name and name.lower() in sources for name in names)


def _history(messages: Sequence[ChatMessageSchema], budget: int) -> list[dict[str, str]]:
    """The question and the earlier messages, newest first, that fit `budget`
    characters; the oldest one kept may be cut, older ones are left out."""
    question = messages[-1]
    kept = [{"role": question.role, "content": question.content}]
    left = budget - len(question.content)
    for message in reversed(messages[:-1]):
        if left <= 0:
            break
        content = message.content
        if len(content) > left:
            content = content[:left].rstrip() + "…"
        kept.append({"role": message.role, "content": content})
        left -= len(content)
    return kept[::-1]


def _context(documents: Sequence[dict[str, object]], budget: int) -> str:
    """Documents for the prompt, within `budget` characters. Past num_ctx
    Ollama silently drops the start of the prompt (the instructions), so the
    documents are cut instead, each to an equal share."""
    named: list[tuple[str, str]] = []
    for document in documents:
        text = str(document.get("text") or "").strip()
        if not text:
            continue
        name = (
            str(document.get("filename") or document.get("name") or "Document").strip()
            or "Document"
        )
        named.append((name, text))
    if not named:
        return ""
    share = budget // len(named)
    parts: list[str] = []
    for name, text in named:
        if len(text) > share:
            text = text[:share].rstrip() + "\n…"
        parts.append(f"Document: {name}\n{text}")
    return "\n\n".join(parts)
