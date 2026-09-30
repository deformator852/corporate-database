from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ChatRequest(Base):
    """One question sent to the assistant, for the chat limits: an open row
    (`finished_at` empty) means an answer is being written, and at most one
    per user may be open (unique index); rows of the last 10 minutes count
    towards CHAT_QUESTIONS_PER_10_MIN. Rows older than a day are deleted."""

    __tablename__ = "chat_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_chat_requests_user_id_started_at", "user_id", "started_at"),
        Index(
            "uq_chat_requests_one_open_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("finished_at IS NULL"),
        ),
    )
