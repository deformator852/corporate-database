from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from encryption import EncryptedText


class DocumentText(Base):
    """Text extracted once at processing time, so chat answers do not re-download
    and re-parse the file for every question. Separate table: document lists
    never load it."""

    __tablename__ = "document_texts"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Encrypted at rest (DATA_ENCRYPTION_KEY); the ORM sees plain text.
    text: Mapped[str] = mapped_column(EncryptedText)
