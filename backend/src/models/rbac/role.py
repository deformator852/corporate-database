from sqlalchemy import CheckConstraint, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from exceptions import AppError
from models.mixins import TimestampMixin


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text)
    users: Mapped[list["User"]] = relationship(
        secondary="role_users",
        back_populates="roles",
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions",
        back_populates="roles",
    )

    __table_args__ = (
        CheckConstraint("length(key) BETWEEN 2 AND 50"),
        CheckConstraint("length(name) BETWEEN 2 AND 100"),
    )


@event.listens_for(Role, "before_delete")
def before_role_delete(mapper, connection, target):
    if target.key == "admin":
        raise AppError(
            "conflict",
            "The Admin role cannot be deleted",
            status_code=409,
        )
