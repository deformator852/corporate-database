from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin


class NotificationType(StrEnum):
    DOCUMENT_COMPLETED = "document.completed"
    DOCUMENT_STORE_FAILED = "document.store_failed"
    DOCUMENT_QUEUE_FAILED = "document.queue_failed"
    DOCUMENT_PROCESS_FAILED = "document.process_failed"


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    type: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped["User"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "type IN ("
            "'document.completed',"
            "'document.store_failed',"
            "'document.queue_failed',"
            "'document.process_failed'"
            ")",
            name="ck_notifications_type",
        ),
    )
