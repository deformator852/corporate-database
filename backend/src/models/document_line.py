from sqlalchemy import ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DocumentLine(Base):
    """Keyed digests of a document's long lines, to find lines that many
    documents share - disclaimers, confidentiality notices - and leave them
    out of search vectors (services/documents/boilerplate.py). Only digests:
    the text stays encrypted in document_texts."""

    __tablename__ = "document_lines"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    digest: Mapped[bytes] = mapped_column(LargeBinary(16), primary_key=True, index=True)
