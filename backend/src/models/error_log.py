from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from encryption import EncryptedText


class ErrorLog(Base):
    """Warnings and errors the backend and the worker logged
    (services/error_log.py), for the Error log page. Deleted after
    ERROR_LOG_RETENTION_DAYS."""

    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(16))
    # backend or worker: the process that logged it.
    source: Mapped[str] = mapped_column(String(16))
    logger: Mapped[str] = mapped_column(String(128))
    # unhandled (a bug: nothing caught it), app (Corpus logged it) or library
    # (a package Corpus uses warned); services/error_log.category_of.
    category: Mapped[str] = mapped_column(String(16), server_default="library")
    # Encrypted: an error can quote a document or a chat.
    message: Mapped[str] = mapped_column(EncryptedText)
    traceback: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)

    __table_args__ = (
        # The page lists newest first, filtered by level and source.
        Index("ix_error_logs_created_at", "created_at"),
        Index("ix_error_logs_level_source_created_at", "level", "source", "created_at"),
        Index("ix_error_logs_category_created_at", "category", "created_at"),
    )
