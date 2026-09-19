from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(unique=True, index=True)
    roles: Mapped[list["Role"]] = relationship(
        secondary="role_users",
        back_populates="users",
    )
    password: Mapped[str]

    __table_args__ = (
        CheckConstraint("length(first_name) BETWEEN 2 AND 100"),
        CheckConstraint("length(last_name) BETWEEN 2 AND 100"),
    )
