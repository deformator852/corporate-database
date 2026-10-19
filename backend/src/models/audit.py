from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AuditAction(StrEnum):
    # Plain strings in the table: extensions may record their own actions.
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGE = "auth.password_change"
    USER_CREATE = "users.create"
    USER_UPDATE = "users.update"
    USER_DELETE = "users.delete"
    USER_DISABLE = "users.disable"
    USER_ENABLE = "users.enable"
    ROLE_CREATE = "roles.create"
    ROLE_UPDATE = "roles.update"
    ROLE_DELETE = "roles.delete"
    DOCUMENT_UPLOAD = "documents.upload"
    DOCUMENT_UPDATE = "documents.update"
    DOCUMENT_RETRY = "documents.retry"
    DOCUMENT_DELETE = "documents.delete"
    DOCUMENT_VIEW = "documents.view"
    CHAT_ANSWER = "chat.answer"
    CHAT_VIEW = "chat.view"
    CHAT_PURGE = "chat.purge"
    CHAT_DELETE = "chat.delete"
    RATING_DELETE = "chat.rating_delete"
    SYSTEM_RECHUNK = "system.rechunk"
    SYSTEM_REINDEX = "system.reindex"


class AuditLog(Base):
    """Append-only record of who did what. No update or delete API."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    # Snapshot of the email so entries survive user deletion.
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    target_label: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))

    __table_args__ = (
        # Login throttling reads recent failures by email and by IP.
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
        # A user's history, newest first (user activity page).
        Index("ix_audit_logs_actor_id_created_at", "actor_id", "created_at", "id"),
        # Failed sign-ins on an account, and login throttling by email.
        Index("ix_audit_logs_actor_email", "actor_email"),
    )
