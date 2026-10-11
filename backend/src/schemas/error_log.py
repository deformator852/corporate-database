from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel

from models.error_log import ErrorLog
from schemas.model_config import ORM_MODEL_CONFIG
from schemas.page import PageSchema

ErrorLevel = Literal["warning", "error", "critical"]
ErrorCategory = Literal["unhandled", "app", "library"]


class ErrorLogItemSchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    created_at: datetime
    level: str
    source: str
    logger: str
    category: str
    message: str
    traceback: str | None


class ErrorLogListSchema(PageSchema):
    items: list[ErrorLogItemSchema]

    @classmethod
    def from_page(cls, entries: list[ErrorLog], *, page: int, per_page: int, total: int) -> Self:
        return cls(
            items=[ErrorLogItemSchema.model_validate(entry) for entry in entries],
            page=page,
            per_page=per_page,
            total=total,
        )
