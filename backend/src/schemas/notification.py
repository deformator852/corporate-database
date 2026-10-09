from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field

from models.notification import Notification, NotificationType
from schemas.model_config import MODEL_CONFIG, ORM_MODEL_CONFIG
from schemas.page import PageSchema


class NotificationSchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    type: NotificationType
    message: str
    read: bool
    created_at: datetime

    @classmethod
    def from_notification(cls, notification: Notification) -> Self:
        return cls.model_validate(notification)


class NotificationListResponseSchema(PageSchema):
    items: list[NotificationSchema]
    unread_count: int

    @classmethod
    def from_page(
        cls,
        notifications: list[Notification],
        *,
        page: int,
        per_page: int,
        total: int,
        unread_count: int,
    ) -> Self:
        return cls(
            items=[NotificationSchema.from_notification(item) for item in notifications],
            page=page,
            per_page=per_page,
            total=total,
            unread_count=unread_count,
        )


class NotificationReadSchema(BaseModel):
    model_config = MODEL_CONFIG

    ids: list[int] = Field(min_length=1, max_length=200)
