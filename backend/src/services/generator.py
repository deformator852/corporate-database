from collections.abc import Sequence

import httpx
from ollama import AsyncClient, RequestError, ResponseError

from exceptions import AppError
from schemas.chat import ChatMessageSchema
from settings import LANGUAGES, language, llm_host, llm_model

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


class OllamaGenerator:
    def __init__(self, client: AsyncClient | None = None) -> None:
        self.client = client or AsyncClient(host=llm_host(), timeout=_TIMEOUT)

    async def complete(
        self,
        messages: Sequence[ChatMessageSchema],
        documents: Sequence[dict[str, object]],
    ) -> str:
        payload = [
            {
                "role": "system",
                "content": _SYSTEM.format(language=LANGUAGES[language()]),
            },
            *_history(messages),
        ]
        context = _context(documents)
        if context:
            payload[-1]["content"] = (
                f"Documents:\n{context}\n\nQuestion:\n{payload[-1]['content']}"
            )
        approx_tokens = max(len(context) // 3, 256)
        try:
            response = await self.client.chat(
                model=llm_model(),
                messages=payload,
                think=False,
                options={
                    "temperature": 0.2,
                    "num_predict": min(8192, max(256, approx_tokens + 64)),
                    "num_ctx": min(32768, max(2048, approx_tokens + 1024)),
                },
            )
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
        content = (response.message.content or "").strip()
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


def _context(documents: Sequence[dict[str, object]]) -> str:
    parts: list[str] = []
    for index, document in enumerate(documents, start=1):
        text = str(document.get("text") or "").strip()
        if not text:
            continue
        name = (
            str(document.get("filename") or document.get("name") or "Document").strip()
            or "Document"
        )
        parts.append(f"[{index}] {name}\n{text}")
    return "\n\n".join(parts)
