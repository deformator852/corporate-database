"""Other users' saved chats, for holders of chat.history (read) and
chat.purge (delete). Like managing users, it reaches only users holding no
permission the actor lacks: answers quote documents of the owner's clearance."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import ColumnElement, CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from exceptions import AppError
from models.chat import ChatConversation, ChatMessageRecord
from models.rbac import role_permissions, role_users
from models.rbac.permission import Permission
from models.rbac.role import Role
from models.user import User
from services.documents.access import user_permission_keys
from services.grant import ensure_can_manage, role_keys


@dataclass(frozen=True, slots=True)
class ReviewedConversation:
    conversation: ChatConversation
    user: User
    message_count: int


@dataclass(frozen=True, slots=True)
class ChatPeriod:
    """Chats last active in [since, until); None leaves that end open."""

    since: datetime | None = None
    until: datetime | None = None

    def conditions(self) -> list[ColumnElement[bool]]:
        found: list[ColumnElement[bool]] = []
        if self.since is not None:
            found.append(ChatConversation.updated_at >= self.since)
        if self.until is not None:
            found.append(ChatConversation.updated_at < self.until)
        return found


class ChatReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_conversations(
        self, actor_id: int, user_id: int | None, page: int, per_page: int
    ) -> tuple[list[ReviewedConversation], int]:
        """Newest activity first; `user_id` limits it to one user."""
        conditions = [await self._reachable(actor_id)]
        if user_id is not None:
            conditions.append(ChatConversation.user_id == user_id)
        total = await self.session.scalar(select(func.count()).select_from(ChatConversation).where(*conditions))
        count = (
            select(func.count())
            .where(ChatMessageRecord.conversation_id == ChatConversation.id)
            .correlate(ChatConversation)
            .scalar_subquery()
        )
        rows = await self.session.execute(
            select(ChatConversation, User, count)
            .join(User, User.id == ChatConversation.user_id)
            .where(*conditions)
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        items = [ReviewedConversation(conversation, user, messages) for conversation, user, messages in rows.tuples()]
        return items, total or 0

    async def get(self, actor_id: int, conversation_id: int) -> ReviewedConversation:
        row = (
            await self.session.execute(
                select(ChatConversation, User)
                .join(User, User.id == ChatConversation.user_id)
                .where(ChatConversation.id == conversation_id, await self._reachable(actor_id))
                .options(selectinload(ChatConversation.messages))
            )
        ).first()
        if row is None:
            raise AppError("not_found", "Conversation not found", status_code=404)
        conversation, user = row.tuple()
        return ReviewedConversation(conversation, user, len(conversation.messages))

    async def purge(self, actor_id: int, user_id: int | None, period: ChatPeriod) -> int:
        """Deletes the chats last active in `period`, whole, with their
        messages and ratings; of one user or of every reachable one."""
        conditions = [await self._reachable(actor_id), *period.conditions()]
        if user_id is not None:
            user = await self.session.scalar(
                select(User).where(User.id == user_id).options(selectinload(User.roles).selectinload(Role.permissions))
            )
            if user is None:
                raise AppError("not_found", "User not found", status_code=404)
            ensure_can_manage(await user_permission_keys(self.session, actor_id), role_keys(user.roles))
            conditions.append(ChatConversation.user_id == user_id)
        result = await self.session.execute(delete(ChatConversation).where(*conditions))
        # A DELETE gives a CursorResult; the async API types it as Result.
        return cast(CursorResult, result).rowcount or 0

    async def _reachable(self, actor_id: int) -> ColumnElement[bool]:
        """Chats of users holding no permission the actor lacks."""
        actor_keys = await user_permission_keys(self.session, actor_id)
        beyond = (
            select(role_users.c.user_id)
            .join(role_permissions, role_permissions.c.role_id == role_users.c.role_id)
            .join(Permission, Permission.id == role_permissions.c.permission_id)
            .where(Permission.key.not_in(actor_keys))
        )
        return ChatConversation.user_id.not_in(beyond)
