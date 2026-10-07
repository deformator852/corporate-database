from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from encryption import EncryptedText


class ChatConversation(Base):
    """A user's saved chat. Private to its owner; deleted after
    CHAT_RETENTION_DAYS without activity."""

    __tablename__ = "chat_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Encrypted: the title is the start of the first question.
    title: Mapped[str] = mapped_column(EncryptedText)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    messages: Mapped[list[ChatMessageRecord]] = relationship(
        order_by="ChatMessageRecord.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_chat_conversations_user_id_updated_at", "user_id", "updated_at"),)


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    # Encrypted: answers quote documents, questions can be confidential too.
    content: Mapped[str] = mapped_column(EncryptedText)
    # Documents the answer was built from: [{id, name, filename}].
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # The owner's rating of an answer: 1 good, -1 bad. A rated answer and its
    # question are shown to users with chat.feedback (the owner is told).
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (CheckConstraint("rating IN (-1, 1)", name="ck_chat_messages_rating"),)
