from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DocumentText(Base):
    """Text extracted once at processing time, so chat answers do not re-download
    and re-parse the file for every question. Separate table: document lists
    never load it."""

    __tablename__ = "document_texts"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    text: Mapped[str] = mapped_column(Text)
