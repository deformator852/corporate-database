from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class RevokedToken(Base):
    """JWTs signed out before expiry. Rows are useless after `expires_at`."""

    __tablename__ = "revoked_tokens"

    # sha256 of the encoded token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
