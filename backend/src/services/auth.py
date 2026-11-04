import asyncio
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
from models.rbac import role_users
from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.role import Role
from models.user import User
from schemas.auth import LoginSchema, PasswordChangeSchema
from security import sessions_cutoff, user_session_valid
from services.audit import AuditService
from services.password import hash_password, uses_password, verify_password
from services.sso import SsoIdentity
from settings import OidcConfig, oidc_config

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
        # An SSO-only account has no password: it fails like a wrong one.
        hashed = user.password if user and user.password else _UNKNOWN_USER_HASH
        # bcrypt takes a quarter second of CPU: in a thread, or every sign-in
        # attempt would stall all other requests and sockets meanwhile.
        password_ok = await asyncio.to_thread(verify_password, data.password, hashed)
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
        if oidc_config() is not None and not _is_admin(user):
            # With single sign-on, only administrators keep their Archfold
            # password: their way in when the company's provider is down.
            # After the password check, so it tells strangers nothing.
            raise AppError("sso_required", "Sign in with SSO.", status_code=403)
        self.audit.record(AuditAction.LOGIN, actor=user)
        return user

    async def sso_login(self, identity: SsoIdentity, config: OidcConfig) -> User:
        """The account of whoever signed in at the provider, created at the
        first sign-in. Matched by the provider's id of the person, never by
        email: an email can be changed or reused to take over an account."""
        user = await self.session.scalar(
            select(User).where(User.oidc_subject == identity.subject).options(_USER_WITH_PERMISSIONS)
        )
        if user is None:
            user = await self._first_sso_login(identity, config)
        elif identity.email_trusted and identity.email and identity.email != user.email:
            # Renamed at the provider: follow, unless another account has it.
            taken = await self.session.scalar(select(User.id).where(User.email == identity.email))
            if taken is None:
                user.email = identity.email
        if user.is_disabled:
            await self._record_failure(user.email)
            raise AppError("account_disabled", "This account is disabled", status_code=403)
        if config.role_map:
            await self._sync_roles(user, identity.groups, config.role_map)
        self.audit.record(AuditAction.LOGIN, actor=user, details={"method": "sso"})
        await self.session.flush()
        return user

    async def _first_sso_login(self, identity: SsoIdentity, config: OidcConfig) -> User:
        if not identity.email:
            raise AppError("invalid", "The SSO provider sent no email address.", status_code=400)
        existing = await self.session.scalar(
            select(User).where(User.email == identity.email).options(_USER_WITH_PERMISSIONS)
        )
        if existing is not None:
            # Only an email the provider vouches for may take over an account.
            if not (config.link_by_email and identity.email_trusted) or existing.oidc_subject is not None:
                raise AppError(
                    "sso_account_exists",
                    "An account with this email already exists. Ask an administrator.",
                    status_code=409,
                )
            existing.oidc_subject = identity.subject
            return existing
        user = User(
            first_name=identity.first_name,
            last_name=identity.last_name,
            email=identity.email,
            password=None,
            oidc_subject=identity.subject,
            roles=[],
        )
        self.session.add(user)
        return user

    async def _sync_roles(self, user: User, groups: list[str], role_map: dict[str, str]) -> None:
        """Mapped roles follow the provider's groups; other roles stay as
        administrators set them."""
        managed = list(await self.session.scalars(select(Role).where(Role.key.in_(set(role_map.values())))))
        wanted = {role_map[group] for group in groups if group in role_map}
        if _is_admin(user) and ADMIN_ROLE_KEY not in wanted and not await self._other_admin_exists(user.id):
            # Left out of the group at the provider, but the only admin: a
            # directory change must not leave Archfold without administrators.
            wanted.add(ADMIN_ROLE_KEY)
        managed_keys = {role.key for role in managed}
        user.roles = [role for role in user.roles if role.key not in managed_keys] + [
            role for role in managed if role.key in wanted
        ]

    async def change_password(self, user: User, data: PasswordChangeSchema) -> None:
        """The user's own password, after the current one. Ends every session
        of the user, this one too: they sign in again with the new password.
        Wrong current passwords count as failed sign-ins (same throttle)."""
        # With roles: with single sign-on, only administrators keep a password.
        loaded = await self.get_with_permissions(user.id)
        if loaded is None or user.password is None or not uses_password(loaded):
            raise AppError("invalid", "This account signs in with SSO and has no password.", status_code=400)
        current = user.password
        await self._ensure_not_throttled(user.email)
        if not await asyncio.to_thread(verify_password, data.current_password, current):
            await self._record_failure(user.email)
            # 400, not 401: the session is fine, and 401 would sign the user out.
            raise AppError("invalid", "The current password is wrong.", status_code=400)
        if data.new_password == data.current_password:
            raise AppError("invalid", "The new password must differ from the current one.", status_code=400)
        user.password = await asyncio.to_thread(hash_password, data.new_password)
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

    async def _other_admin_exists(self, user_id: int) -> bool:
        found = await self.session.scalar(
            select(role_users.c.user_id)
            .join(Role, Role.id == role_users.c.role_id)
            .join(User, User.id == role_users.c.user_id)
            .where(Role.key == ADMIN_ROLE_KEY, User.disabled_at.is_(None), User.id != user_id)
            .limit(1)
        )
        return found is not None

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


def _is_admin(user: User) -> bool:
    return any(role.key == ADMIN_ROLE_KEY for role in user.roles)
