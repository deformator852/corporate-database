from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit import AuditAction, AuditLog
from models.user import User


class AuditService:
    """Adds entries to the caller's session, so they commit with the action."""

    def __init__(self, session: AsyncSession, ip: str | None = None) -> None:
        self.session = session
        self.ip = ip

    def record(
        self,
        action: str,
        *,
        actor: User | None = None,
        actor_email: str | None = None,
        target_type: str | None = None,
        target_id: object = None,
        target_label: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor.id if actor else None,
                actor_email=actor.email if actor else actor_email,
                action=str(action),
                target_type=target_type,
                target_id=None if target_id is None else str(target_id),
                target_label=target_label[:255] if target_label else None,
                details=details or {},
                ip=self.ip,
            )
        )

    async def list_entries(
        self,
        page: int = 1,
        per_page: int = 20,
        q: str = "",
        action: str = "",
    ) -> tuple[list[AuditLog], int]:
        filters = []
        if action:
            filters.append(AuditLog.action == action)
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    AuditLog.actor_email.ilike(pattern),
                    AuditLog.target_label.ilike(pattern),
                    AuditLog.ip.ilike(pattern),
                )
            )
        total = await self.session.scalar(
            select(func.count()).select_from(AuditLog).where(*filters)
        )
        entries = await self.session.scalars(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(entries), total or 0

    async def failed_logins_since(
        self, since: datetime, *, email: str | None = None, ip: str | None = None
    ) -> int:
        """Failed sign-ins after `since` and after the last success for the
        same email or IP (a success resets the count)."""
        column = AuditLog.actor_email if email is not None else AuditLog.ip
        value = email if email is not None else ip
        last_success = await self.session.scalar(
            select(func.max(AuditLog.created_at)).where(
                AuditLog.action == AuditAction.LOGIN,
                column == value,
            )
        )
        start = max(since, last_success) if last_success else since
        count = await self.session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == AuditAction.LOGIN_FAILED,
                column == value,
                AuditLog.created_at > start,
            )
        )
        return count or 0
