from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from exceptions import AppError
from models.chat import ChatConversation, ChatMessageRecord

_TITLE_CHARS = 80


class ChatHistoryService:
    """Saved chats. Every lookup is scoped to the owner: a user can never
    read or delete another user's conversation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_conversations(
        self, user_id: int, page: int = 1, per_page: int = 20
    ) -> tuple[list[ChatConversation], int]:
        owned = ChatConversation.user_id == user_id
        total = await self.session.scalar(select(func.count()).select_from(ChatConversation).where(owned))
        items = await self.session.scalars(
            select(ChatConversation)
            .where(owned)
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(items), total or 0

    async def get(self, user_id: int, conversation_id: int) -> ChatConversation:
        conversation = await self.session.scalar(
            select(ChatConversation)
            .where(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id,
            )
            .options(selectinload(ChatConversation.messages))
        )
        if conversation is None:
            raise AppError("not_found", "Conversation not found", status_code=404)
        return conversation

    async def open_or_start(self, user_id: int, conversation_id: int | None, question: str) -> ChatConversation:
        if conversation_id is not None:
            return await self.get(user_id, conversation_id)
        title = " ".join(question.split())
        if len(title) > _TITLE_CHARS:
            title = title[: _TITLE_CHARS - 1].rstrip() + "…"
        conversation = ChatConversation(user_id=user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def add_message(
        self,
        conversation: ChatConversation,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> None:
        self.session.add(
            ChatMessageRecord(
                conversation_id=conversation.id,
                role=role,
                content=content,
                sources=sources or [],
            )
        )
        conversation.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def delete(self, user_id: int, conversation_id: int) -> None:
        conversation = await self.get(user_id, conversation_id)
        await self.session.delete(conversation)

    async def purge_older_than(self, days: int) -> int:
        """Deletes conversations idle for `days`; messages go with them."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(delete(ChatConversation).where(ChatConversation.updated_at < cutoff))
        await self.session.commit()
        # A DELETE gives a CursorResult; the async API types it as Result.
        return cast(CursorResult, result).rowcount or 0
