from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, LargeBinary, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:  # relationships only; the real import would be circular
    from models.user import User


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


# Processing is over; any other status means the document still waits.
DONE_STATUSES = (DocumentStatus.COMPLETED, DocumentStatus.FAILED)


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
    user: Mapped[User | None] = relationship()
    # Keyed digest of the uploaded bytes, to refuse the same file twice;
    # without the key it tells nothing about the content.
    content_digest: Mapped[bytes | None] = mapped_column(LargeBinary(16), index=True)
    # Completed, but the owner has not been told yet: told in one notice
    # once none of their documents is waiting (services/notifications).
    ready_unannounced: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Its index is being rebuilt. For another embedding model (uv run
    # switch-embedding-model) it is queued again, and being ready again is not
    # news to the owner; to re-chunk it (System page) it stays completed and
    # searchable meanwhile (processor.rechunk).
    reindexing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # CHUNK_SIZE / CHUNK_OVERLAP its chunks were cut with: after a change in
    # `uv run configure`, the ones cut otherwise can be re-chunked (System page).
    chunk_size: Mapped[int | None] = mapped_column(Integer)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 200"),
        CheckConstraint("progress BETWEEN 0 AND 100"),
        CheckConstraint("status IN ('queued','parsing','chunking','embedding','completed','failed')"),
        CheckConstraint(
            "classification IN ('standard','restricted','confidential','secret')",
            name="ck_documents_classification",
        ),
    )
