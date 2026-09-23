from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentClassification(StrEnum):
    STANDARD = "standard"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.QUEUED)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_key: Mapped[str] = mapped_column(String(500))
    classification: Mapped[str] = mapped_column(
        String(20),
        default=DocumentClassification.STANDARD,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 200"),
        CheckConstraint("progress BETWEEN 0 AND 100"),
        CheckConstraint(
            "status IN ('queued','parsing','chunking','embedding','completed','failed')"
        ),
        CheckConstraint(
            "classification IN ('standard','restricted','confidential','secret')",
            name="ck_documents_classification",
        ),
    )
