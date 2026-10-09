from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel

from models.audit import AuditLog
from schemas.model_config import MODEL_CONFIG, ORM_MODEL_CONFIG
from schemas.page import PageSchema


class AuditEntrySchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    created_at: datetime
    actor_id: int | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    target_label: str | None
    details: dict[str, Any]
    ip: str | None


class AuditListResponseSchema(PageSchema):
    items: list[AuditEntrySchema]

    @classmethod
    def from_page(cls, entries: list[AuditLog], *, page: int, per_page: int, total: int) -> Self:
        return cls(
            items=[AuditEntrySchema.model_validate(entry) for entry in entries],
            page=page,
            per_page=per_page,
            total=total,
        )


class AuditCursorPageSchema(BaseModel):
    """Infinite-scroll page: pass `next_cursor` back as `before`."""

    model_config = MODEL_CONFIG

    items: list[AuditEntrySchema]
    next_cursor: int | None

    @classmethod
    def from_entries(cls, entries: list[AuditLog], next_cursor: int | None) -> Self:
        return cls(
            items=[AuditEntrySchema.model_validate(entry) for entry in entries],
            next_cursor=next_cursor,
        )
