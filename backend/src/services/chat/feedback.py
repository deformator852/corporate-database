"""Ratings of the assistant's answers: the owner rates an answer good or bad,
and users with chat.feedback read the rated answers with their questions, to
see where the assistant goes wrong on real documents. Unrated chats stay
private to their owner."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.chat import ChatConversation, ChatMessageRecord
from models.user import User


@dataclass(frozen=True, slots=True)
class RatedAnswer:
    message_id: int
    conversation_id: int
    rating: int
    question: str
    answer: str
    sources: list[dict[str, Any]]
    rated_at: datetime
    user: User | None


class FeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rate(self, user_id: int, conversation_id: int, message_id: int, rating: int | None) -> None:
        """Rates one of the user's own answers; None takes the rating back."""
        message = await self.session.scalar(
            select(ChatMessageRecord)
            .join(ChatConversation, ChatConversation.id == ChatMessageRecord.conversation_id)
            .where(
                ChatMessageRecord.id == message_id,
                ChatMessageRecord.conversation_id == conversation_id,
                ChatMessageRecord.role == "assistant",
                ChatConversation.user_id == user_id,
            )
        )
        if message is None:
            raise AppError("not_found", "Answer not found", status_code=404)
        message.rating = rating
        message.rated_at = datetime.now(UTC) if rating is not None else None
        await self.session.commit()

    async def remove_rating(self, message_id: int) -> tuple[ChatMessageRecord, User | None]:
        """Takes a rated answer off the ratings page (handled, say); the chat
        and the answer stay. Returns it and its owner, for the audit log."""
        row = (
            await self.session.execute(
                select(ChatMessageRecord, User)
                .join(ChatConversation, ChatConversation.id == ChatMessageRecord.conversation_id)
                .outerjoin(User, User.id == ChatConversation.user_id)
                .where(ChatMessageRecord.id == message_id, ChatMessageRecord.rating.is_not(None))
            )
        ).first()
        if row is None:
            raise AppError("not_found", "Answer not found", status_code=404)
        message, owner = row.tuple()
        message.rating = None
        message.rated_at = None
        return message, owner

    async def rated(self, rating: int | None, page: int, per_page: int) -> tuple[list[RatedAnswer], int]:
        """Answers with `rating` (None: every rated answer), newest rating first."""
        rated = ChatMessageRecord.rating.is_not(None) if rating is None else ChatMessageRecord.rating == rating
        total = await self.session.scalar(select(func.count()).select_from(ChatMessageRecord).where(rated))
        rows = await self.session.execute(
            select(ChatMessageRecord, User)
            .join(ChatConversation, ChatConversation.id == ChatMessageRecord.conversation_id)
            .outerjoin(User, User.id == ChatConversation.user_id)
            .where(rated)
            .order_by(ChatMessageRecord.rated_at.desc(), ChatMessageRecord.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        items: list[RatedAnswer] = []
        for answer, user in rows.tuples():
            items.append(
                RatedAnswer(
                    message_id=answer.id,
                    conversation_id=answer.conversation_id,
                    rating=answer.rating or 0,
                    question=await self._question_of(answer),
                    answer=answer.content,
                    sources=answer.sources,
                    rated_at=answer.rated_at or answer.created_at,
                    user=user,
                )
            )
        return items, total or 0

    async def _question_of(self, answer: ChatMessageRecord) -> str:
        """The user's message the answer replied to: the last one before it."""
        question = await self.session.scalar(
            select(ChatMessageRecord.content)
            .where(
                ChatMessageRecord.conversation_id == answer.conversation_id,
                ChatMessageRecord.role == "user",
                ChatMessageRecord.id < answer.id,
            )
            .order_by(ChatMessageRecord.id.desc())
            .limit(1)
        )
        return question or ""
