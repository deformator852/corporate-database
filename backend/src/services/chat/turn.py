"""One question and its answer in a saved chat: what the chat socket runs
for each question (api/v1/chat.py keeps only the socket protocol)."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models.audit import AuditAction
from models.user import User
from schemas.chat import ChatMessageSchema
from services.audit import AuditService
from services.chat.chat import ChatService
from services.chat.context_document import ContextDocument
from services.chat.generator import OllamaGenerator, OnDelta
from services.chat.history import ChatHistoryService
from services.search.embedding import EmbeddingModel


@dataclass(frozen=True, slots=True)
class AnsweredTurn:
    conversation_id: int
    content: str
    sources: list[ContextDocument]


async def answer_question(
    user_id: int,
    messages: list[ChatMessageSchema],
    conversation_id: int | None,
    *,
    ip: str | None,
    embedder: EmbeddingModel,
    generator: OllamaGenerator,
    on_delta: OnDelta,
) -> AnsweredTurn:
    """Saves the question, answers it (streaming to `on_delta`), saves the
    answer with its sources and records which documents were read."""
    async with AsyncSessionLocal() as session:
        history = ChatHistoryService(session)
        question = messages[-1].content
        # Saved before answering: the question is kept even if the answer
        # fails or is cancelled.
        conversation = await history.open_or_start(user_id, conversation_id, question)
        await history.add_message(conversation, "user", question)
        await session.commit()

        content, sources, read = await ChatService(session, embedder, generator).reply(user_id, messages, on_delta)
        await history.add_message(
            conversation,
            "assistant",
            content,
            [{"id": d.document_id, "name": d.name, "filename": d.filename} for d in sources],
        )
        if read:
            await _audit_reading(session, user_id, ip, read)
        await session.commit()
        return AnsweredTurn(conversation_id=conversation.id, content=content, sources=sources)


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
