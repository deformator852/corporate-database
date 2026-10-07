"""One question and its answer in a saved chat: what the chat socket runs
for each question (api/v1/chat.py keeps only the socket protocol)."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models.audit import AuditAction
from models.chat import ChatConversation, ChatMessageRecord
from models.user import User
from schemas.chat import ChatAskSchema
from services.audit import AuditService
from services.chat.chat import ChatService
from services.chat.context_document import ContextDocument
from services.chat.generator import OllamaGenerator, OnDelta
from services.chat.history import ChatHistoryService
from services.search.embedding import EmbeddingModel


@dataclass(frozen=True, slots=True)
class AnsweredTurn:
    conversation_id: int
    message_id: int
    content: str
    # As saved with the answer: {id, name, filename, chunk}.
    sources: list[dict[str, Any]]


async def answer_question(
    user_id: int,
    ask: ChatAskSchema,
    *,
    ip: str | None,
    embedder: EmbeddingModel,
    generator: OllamaGenerator,
    on_delta: OnDelta,
    on_started: Callable[[int], Awaitable[None]],
) -> AnsweredTurn:
    """Saves the question (telling `on_started` its chat), answers it
    (streaming to `on_delta`), saves the answer with its sources and records
    which documents were read. Stopped midway, it saves what was written.
    Regenerating, the new answer replaces the old one once it is saved."""
    async with AsyncSessionLocal() as session:
        history = ChatHistoryService(session)
        question = ask.messages[-1].content
        conversation = await history.open_or_start(user_id, ask.conversation_id, question)
        replaced = None
        if ask.replace_message_id is not None:
            replaced = history.last_answer(conversation, ask.replace_message_id)
        else:
            # Saved before answering: the question is kept even if the answer
            # fails or is cancelled.
            await history.add_message(conversation, "user", question)
            await session.commit()
        await on_started(conversation.id)

        written: list[str] = []

        async def stream(piece: str) -> None:
            written.append(piece)
            await on_delta(piece)

        chat = ChatService(session, embedder, generator)
        try:
            content, sources, read = await chat.reply(user_id, ask.messages, stream, document_ids=ask.document_ids)
            citations = await chat.cite(user_id, content, sources)
        except asyncio.CancelledError:
            # Stopped: keep what the user already saw, as the chat shows it.
            if "".join(written).strip():
                await asyncio.shield(_save_stopped(history, conversation, "".join(written).strip(), replaced))
            raise
        saved_sources = [
            {"id": d.document_id, "name": d.name, "filename": d.filename, "chunk": citations.get(d.document_id)}
            for d in sources
        ]
        if replaced is not None:
            await session.delete(replaced)
        answer = await history.add_message(conversation, "assistant", content, saved_sources)
        if read:
            await _audit_reading(session, user_id, ip, read)
        await session.commit()
        return AnsweredTurn(
            conversation_id=conversation.id, message_id=answer.id, content=content, sources=saved_sources
        )


async def _save_stopped(
    history: ChatHistoryService, conversation: ChatConversation, text: str, replaced: ChatMessageRecord | None
) -> None:
    if replaced is not None:
        await history.session.delete(replaced)
    await history.add_message(conversation, "assistant", text)
    await history.session.commit()


async def _audit_reading(session: AsyncSession, user_id: int, ip: str | None, read: list[ContextDocument]) -> None:
    """Who read which documents through the assistant; not the question."""
    AuditService(session, ip).record(
        AuditAction.CHAT_ANSWER,
        actor=await session.get(User, user_id),
        target_type="document",
        target_label=", ".join(d.name for d in read),
        details={
            "documents": [{"id": d.document_id, "name": d.name, "classification": d.classification} for d in read]
        },
    )
