import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.role import Role
from models.user import User
from services.password import hash_password, verify_password

ADMIN_EMAIL = "admin@local.test"
# Accounts older seeders created with the password "password".
_LEGACY_ACCOUNTS = (ADMIN_EMAIL, "dev@local.test")
_LEGACY_PASSWORD = "password"


async def seed_users(session: AsyncSession) -> None:
    if await session.scalar(select(User.id).limit(1)) is None:
        password = secrets.token_urlsafe(12)
        session.add(
            User(
                first_name="Admin",
                last_name="Admin",
                email=ADMIN_EMAIL,
                password=hash_password(password),
            )
        )
        await session.flush()
        _announce(ADMIN_EMAIL, password)
    else:
        await _replace_legacy_passwords(session)

    admin_role = await session.scalar(select(Role).where(Role.key == ADMIN_ROLE_KEY))
    admin_user = await session.scalar(
        select(User)
        .where(User.email == ADMIN_EMAIL)
        .options(selectinload(User.roles))
    )
    if admin_role is None or admin_user is None:
        return
    if admin_role not in admin_user.roles:
        admin_user.roles.append(admin_role)


async def _replace_legacy_passwords(session: AsyncSession) -> None:
    users = await session.scalars(select(User).where(User.email.in_(_LEGACY_ACCOUNTS)))
    for user in users:
        if not verify_password(_LEGACY_PASSWORD, user.password):
            continue
        password = secrets.token_urlsafe(12)
        user.password = hash_password(password)
        user.sessions_valid_after = datetime.now(UTC)
        _announce(user.email, password)


def _announce(email: str, password: str) -> None:
    # Shown once; only the hash is stored.
    print(f"Sign in as {email} with password: {password}")
    print("Change it after signing in (Users page). It is not shown again.")
