from collections.abc import Sequence

import httpx
from ollama import AsyncClient, RequestError, ResponseError

from exceptions import AppError
from i18n import current_language
from schemas.chat import ChatMessageSchema
from services.chat.answer_sources import SOURCES_RULE, HideSourcesLine, OnDelta, sources_of
from services.chat.context_document import ContextDocument
from settings import LANGUAGES, llm_host, llm_model, llm_num_ctx

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
    the prompt; longer ones are sent as excerpts (services/chat/chat.py)."""
    budget = _documents_tokens(llm_num_ctx()) * _CHARS_PER_TOKEN
    return budget // max(documents, 1)


class OllamaGenerator:
    def __init__(self, client: AsyncClient | None = None) -> None:
        self.client = client or AsyncClient(host=llm_host(), timeout=_TIMEOUT)

    async def warm_up(self) -> None:
        """Loads the model with the same num_ctx chat uses, so the first
        question does not wait for it."""
        await self.client.generate(model=llm_model(), prompt="", options={"num_ctx": llm_num_ctx()})

    async def complete(
        self,
        messages: Sequence[ChatMessageSchema],
        documents: Sequence[ContextDocument],
        on_delta: OnDelta | None = None,
    ) -> tuple[str, list[ContextDocument]]:
        """The answer and the documents it used: named in the model's sources
        line (every document when the line is missing) and holding facts of
        the answer. Each piece of the answer also goes to `on_delta` as it is
        generated, without the sources line."""
        num_ctx = llm_num_ctx()
        num_predict = num_ctx // 4
        payload = [
            {
                "role": "system",
                "content": _SYSTEM.format(language=LANGUAGES[current_language()]),
            },
            *_history(messages, num_ctx // 4 * _CHARS_PER_TOKEN),
        ]
        budget = _documents_tokens(num_ctx) * _CHARS_PER_TOKEN
        context = _context(documents, budget)
        if context:
            payload[-1]["content"] = f"Documents:\n{context}\n\nQuestion:\n{payload[-1]['content']}\n\n{SOURCES_RULE}"
        parts: list[str] = []
        stream_out = HideSourcesLine(on_delta)
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
        content, used = sources_of("".join(parts), messages[-1].content, documents if context else [])
        if not content:
            raise AppError(
                "unavailable",
                "The chat model returned an empty answer.",
                status_code=503,
            )
        return content, used


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


def _context(documents: Sequence[ContextDocument], budget: int) -> str:
    """Documents for the prompt, within `budget` characters. Past num_ctx
    Ollama silently drops the start of the prompt (the instructions), so the
    documents are cut instead, each to an equal share."""
    named = [(document.label, document.text.strip()) for document in documents if document.text.strip()]
    if not named:
        return ""
    share = budget // len(named)
    parts: list[str] = []
    for name, text in named:
        if len(text) > share:
            text = text[:share].rstrip() + "\n…"
        parts.append(f"Document: {name}\n{text}")
    return "\n\n".join(parts)
