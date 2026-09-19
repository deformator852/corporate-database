from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:
    from models.rbac.permission import Permission


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text)
    permissions: Mapped[list[Permission]] = relationship(back_populates="role")

    __table_args__ = (
        CheckConstraint("length(key) BETWEEN 2 AND 50"),
        CheckConstraint("length(name) BETWEEN 2 AND 100"),
    )
