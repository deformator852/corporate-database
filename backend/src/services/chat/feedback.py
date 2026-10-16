"""Ratings of the assistant's answers: the owner rates an answer good or bad,
and users with chat.feedback read the rated answers with their questions, to
see where the assistant goes wrong on real documents. Unrated chats stay
private to their owner. A reviewer sees only the answers of users whose
documents they may read too: an answer quotes the owner's documents."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.chat import ChatConversation, ChatMessageRecord
from models.rbac import role_permissions, role_users
from models.rbac.permission import Permission
from models.user import User
from services.documents.access import clearance_beyond, user_permission_keys


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

    async def remove_rating(self, actor_id: int, message_id: int) -> tuple[ChatMessageRecord, User | None]:
        """Takes a rated answer off the ratings page (handled, say); the chat
        and the answer stay. Returns it and its owner, for the audit log."""
        row = (
            await self.session.execute(
                select(ChatMessageRecord, User)
                .join(ChatConversation, ChatConversation.id == ChatMessageRecord.conversation_id)
                .outerjoin(User, User.id == ChatConversation.user_id)
                .where(
                    ChatMessageRecord.id == message_id,
                    ChatMessageRecord.rating.is_not(None),
                    await self._within_clearance(actor_id),
                )
            )
        ).first()
        if row is None:
            raise AppError("not_found", "Answer not found", status_code=404)
        message, owner = row.tuple()
        message.rating = None
        message.rated_at = None
        return message, owner

    async def rated(self, actor_id: int, rating: int | None, page: int, per_page: int) -> tuple[list[RatedAnswer], int]:
        """Answers with `rating` (None: every rated answer) that the actor may
        read, newest rating first."""
        rated = ChatMessageRecord.rating.is_not(None) if rating is None else ChatMessageRecord.rating == rating
        visible = await self._within_clearance(actor_id)
        total = await self.session.scalar(
            select(func.count())
            .select_from(ChatMessageRecord)
            .join(ChatConversation, ChatConversation.id == ChatMessageRecord.conversation_id)
            .where(rated, visible)
        )
        rows = await self.session.execute(
            select(ChatMessageRecord, User)
            .join(ChatConversation, ChatConversation.id == ChatMessageRecord.conversation_id)
            .outerjoin(User, User.id == ChatConversation.user_id)
            .where(rated, visible)
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

    async def _within_clearance(self, actor_id: int) -> ColumnElement[bool]:
        """Chats of users holding no document access the actor lacks."""
        beyond = clearance_beyond(await user_permission_keys(self.session, actor_id))
        holders = (
            select(role_users.c.user_id)
            .join(role_permissions, role_permissions.c.role_id == role_users.c.role_id)
            .join(Permission, Permission.id == role_permissions.c.permission_id)
            .where(Permission.key.in_(beyond))
        )
        return ChatConversation.user_id.not_in(holders)

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
