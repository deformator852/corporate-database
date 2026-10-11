from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:  # relationships only; the real import would be circular
    from models.rbac.role import Role


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(unique=True, index=True)
    roles: Mapped[list[Role]] = relationship(
        secondary="role_users",
        back_populates="users",
    )
    # None: signs in only through SSO (created at the first SSO sign-in).
    password: Mapped[str | None]
    # "ISSUER SUBJECT" of the SSO account: the provider's own, unchanging id
    # of the person. Emails change and get reused, so they never identify.
    oidc_subject: Mapped[str | None] = mapped_column(String(512), unique=True)
    # Tokens issued before this moment are rejected (password change).
    sessions_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set: the account cannot sign in; it and its history stay (offboarding).
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Chosen in the header, one of APP_LANGUAGES; None: the default language.
    language: Mapped[str | None] = mapped_column(String(8))

    @property
    def is_disabled(self) -> bool:
        return self.disabled_at is not None

    __table_args__ = (
        CheckConstraint("length(first_name) BETWEEN 2 AND 100"),
        CheckConstraint("length(last_name) BETWEEN 2 AND 100"),
    )
