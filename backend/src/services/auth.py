import secrets
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
from schemas.auth import LoginSchema, PasswordChangeSchema
from security import sessions_cutoff, user_session_valid
from services.audit import AuditService
from services.password import hash_password, verify_password

_USER_WITH_PERMISSIONS = selectinload(User.roles).selectinload(Role.permissions)

# Failed sign-ins allowed per window before sign-in is refused. A success
# resets the count. Per email stops guessing one account; per IP stops
# spraying many accounts from one machine.
LOGIN_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 5
_UNKNOWN_USER_HASH = hash_password(secrets.token_urlsafe(16))
# High: terminal servers, VPN and NAT put many users behind one address.
MAX_FAILURES_PER_IP = 200


class AuthService:
    def __init__(self, session: AsyncSession, audit: AuditService):
        self.session = session
        self.audit = audit

    async def login(self, data: LoginSchema) -> User:
        await self._ensure_not_throttled(data.email)
        user = await self.session.scalar(select(User).where(User.email == data.email).options(_USER_WITH_PERMISSIONS))
        # An unknown email is checked against a stand-in hash: answering
        # faster would tell which emails have accounts.
        password_ok = verify_password(data.password, user.password if user else _UNKNOWN_USER_HASH)
        if user is None or not password_ok:
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

    async def change_password(self, user: User, data: PasswordChangeSchema) -> None:
        """The user's own password, after the current one. Ends every session
        of the user, this one too: they sign in again with the new password.
        Wrong current passwords count as failed sign-ins (same throttle)."""
        await self._ensure_not_throttled(user.email)
        if not verify_password(data.current_password, user.password):
            await self._record_failure(user.email)
            # 400, not 401: the session is fine, and 401 would sign the user out.
            raise AppError("invalid", "The current password is wrong.", status_code=400)
        if data.new_password == data.current_password:
            raise AppError("invalid", "The new password must differ from the current one.", status_code=400)
        user.password = hash_password(data.new_password)
        user.sessions_valid_after = sessions_cutoff()
        self.audit.record(AuditAction.PASSWORD_CHANGE, actor=user)

    async def session_user(self, payload: TokenPayload) -> User | None:
        """The token's user, or None if deleted, disabled or signed out by a password change."""
        try:
            user_id = int(payload.sub)
        except TypeError, ValueError:
            return None
        user = await self.session.get(User, user_id)
        return user if user_session_valid(user, payload) else None

    async def get_with_permissions(self, user_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id).options(_USER_WITH_PERMISSIONS))

    async def _ensure_not_throttled(self, email: str) -> None:
        since = datetime.now(UTC) - LOGIN_WINDOW
        by_email = await self.audit.failed_logins_since(since, email=email)
        by_ip = await self.audit.failed_logins_since(since, ip=self.audit.ip) if self.audit.ip else 0
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
            AuditService(session, self.audit.ip).record(AuditAction.LOGIN_FAILED, actor_email=email)
            await session.commit()
