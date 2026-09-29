from collections.abc import Awaitable, Callable, Sequence

import httpx
from ollama import AsyncClient, RequestError, ResponseError

from exceptions import AppError
from schemas.chat import ChatMessageSchema
from settings import LANGUAGES, language, llm_host, llm_model, llm_num_ctx

_HISTORY = 6
_HISTORY_CHARS = 1500
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
    "invent sources."
)


OnDelta = Callable[[str], Awaitable[None]]

# Rough chars per token for budgeting (Latin ~4, Cyrillic ~2.5).
_CHARS_PER_TOKEN = 3
# Room for the system prompt and chat history.
_PROMPT_OVERHEAD_TOKENS = 1536


def document_budget_chars(documents: int) -> int:
    """Characters of document text one of `documents` documents may take in
    the prompt; longer ones are sent as excerpts (services/chat.py)."""
    num_ctx = llm_num_ctx()
    budget = (num_ctx - num_ctx // 4 - _PROMPT_OVERHEAD_TOKENS) * _CHARS_PER_TOKEN
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
        documents: Sequence[dict[str, object]],
        on_delta: OnDelta | None = None,
    ) -> str:
        """Full answer; each piece also goes to `on_delta` as it is generated."""
        num_ctx = llm_num_ctx()
        num_predict = num_ctx // 4
        payload = [
            {
                "role": "system",
                "content": _SYSTEM.format(language=LANGUAGES[language()]),
            },
            *_history(messages),
        ]
        budget = (num_ctx - num_predict - _PROMPT_OVERHEAD_TOKENS) * _CHARS_PER_TOKEN
        context = _context(documents, budget)
        if context:
            payload[-1]["content"] = (
                f"Documents:\n{context}\n\nQuestion:\n{payload[-1]['content']}"
            )
        parts: list[str] = []
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
                if on_delta is not None:
                    await on_delta(piece)
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
        content = "".join(parts).strip()
        if not content:
            raise AppError(
                "unavailable",
                "The chat model returned an empty answer.",
                status_code=503,
            )
        return content


def _history(messages: Sequence[ChatMessageSchema]) -> list[dict[str, str]]:
    selected = list(messages[-_HISTORY:])
    payload: list[dict[str, str]] = []
    last_index = len(selected) - 1
    for index, message in enumerate(selected):
        content = message.content
        if index != last_index and len(content) > _HISTORY_CHARS:
            content = content[:_HISTORY_CHARS].rstrip() + "…"
        payload.append({"role": message.role, "content": content})
    return payload


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
    for index, (name, text) in enumerate(named, start=1):
        if len(text) > share:
            text = text[:share].rstrip() + "\n…"
        parts.append(f"[{index}] {name}\n{text}")
    return "\n\n".join(parts)
