from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AppError
from models.notification import Notification, NotificationType
from services.notifications.events import NotificationEventPublisher


class NotificationService:
    def __init__(
        self,
        session: AsyncSession,
        publisher: NotificationEventPublisher | None = None,
    ) -> None:
        self.session = session
        self.publisher = publisher

    async def list_notifications(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Notification], int, int]:
        filters = Notification.user_id == user_id
        total = await self.session.scalar(
            select(func.count()).select_from(Notification).where(filters)
        )
        unread_count = await self.session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(filters, Notification.read.is_(False))
        )
        items = await self.session.scalars(
            select(Notification)
            .where(filters)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(items), total or 0, unread_count or 0

    async def create(
        self,
        user_id: int,
        type: NotificationType,
        message: str,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type,
            message=message,
            read=False,
        )
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def mark_read(self, user_id: int, ids: list[int]) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.id.in_(ids),
                Notification.read.is_(False),
            )
            .values(read=True)
        )
        await self.session.commit()

    async def delete(self, user_id: int, notification_id: int) -> None:
        """Dismisses one of the user's own notifications."""
        notification = await self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        if notification is None:
            raise AppError("not_found", "Notification not found", status_code=404)
        await self.session.delete(notification)
        await self.session.commit()

    async def clear(self, user_id: int) -> None:
        items = await self.session.scalars(
            select(Notification).where(Notification.user_id == user_id)
        )
        for item in items:
            await self.session.delete(item)
        await self.session.commit()

    async def emit(self, notification: Notification) -> None:
        publisher = self.publisher
        owned = False
        if publisher is None:
            publisher = NotificationEventPublisher()
            owned = True
        try:
            await publisher.publish(notification)
        except Exception:
            pass
        finally:
            if owned:
                await publisher.close()
