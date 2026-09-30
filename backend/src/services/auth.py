from datetime import UTC, datetime, timedelta

from authx.schema import TokenPayload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal
from exceptions import AppError
from i18n import t
from models.audit import AuditAction
from models.rbac.role import Role
from models.user import User
from schemas.auth import LoginSchema
from security import user_session_valid
from services.audit import AuditService
from services.password import verify_password

_USER_WITH_PERMISSIONS = selectinload(User.roles).selectinload(Role.permissions)

# Failed sign-ins allowed per window before sign-in is refused. A success
# resets the count. Per email stops guessing one account; per IP stops
# spraying many accounts from one machine.
LOGIN_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 20


class AuthService:
    def __init__(self, session: AsyncSession, audit: AuditService):
        self.session = session
        self.audit = audit

    async def login(self, data: LoginSchema) -> User:
        await self._ensure_not_throttled(data.email)
        user = await self.session.scalar(
            select(User)
            .where(User.email == data.email)
            .options(_USER_WITH_PERMISSIONS)
        )
        if user is None or not verify_password(data.password, user.password):
            await self._record_failure(data.email)
            raise AppError(
                "invalid_credentials",
                "Email or password is wrong",
                status_code=401,
            )
        if user.is_disabled:
            # Only after the right password: the message must not tell
            # strangers which emails exist.
            await self._record_failure(data.email)
            raise AppError("account_disabled", "This account is disabled", status_code=403)
        self.audit.record(AuditAction.LOGIN, actor=user)
        return user

    async def session_user(self, payload: TokenPayload) -> User | None:
        """The token's user, or None if deleted, disabled or signed out by a password change."""
        try:
            user_id = int(payload.sub)
        except (TypeError, ValueError):
            return None
        user = await self.session.get(User, user_id)
        return user if user_session_valid(user, payload) else None

    async def get_with_permissions(self, user_id: int) -> User | None:
        return await self.session.scalar(
            select(User).where(User.id == user_id).options(_USER_WITH_PERMISSIONS)
        )

    async def _ensure_not_throttled(self, email: str) -> None:
        since = datetime.now(UTC) - LOGIN_WINDOW
        by_email = await self.audit.failed_logins_since(since, email=email)
        by_ip = (
            await self.audit.failed_logins_since(since, ip=self.audit.ip)
            if self.audit.ip
            else 0
        )
        if by_email >= MAX_FAILURES_PER_EMAIL or by_ip >= MAX_FAILURES_PER_IP:
            minutes = int(LOGIN_WINDOW.total_seconds() // 60)
            raise AppError(
                "rate_limited",
                t(
                    "Too many failed sign-in attempts. Try again in {minutes} minutes.",
                    minutes=minutes,
                ),
                status_code=429,
            )

    async def _record_failure(self, email: str) -> None:
        # Own session: the request session rolls back with the error below.
        async with AsyncSessionLocal() as session:
            AuditService(session, self.audit.ip).record(
                AuditAction.LOGIN_FAILED, actor_email=email
            )
            await session.commit()
