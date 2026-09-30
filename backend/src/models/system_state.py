from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SystemState(Base):
    """Small facts about the installation itself (e.g. which encryption key
    the stored data belongs to). Never secrets."""

    __tablename__ = "system_state"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
