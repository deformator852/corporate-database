"""Creates an administrator: the first account of a new installation.

    python -m maintenance.create_admin admin@company.com [First] [Last]

Prints a random password once; only its hash is stored. Change it after
signing in (Users page). Refuses an email that already exists.
"""

import asyncio
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal, engine
from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.role import Role
from models.user import User
from services.password import hash_password


async def create_admin(email: str, first_name: str, last_name: str) -> str:
    password = secrets.token_urlsafe(12)
    try:
        async with AsyncSessionLocal() as session:
            if await session.scalar(select(User.id).where(User.email == email)):
                raise SystemExit(f"A user with email {email} already exists.")
            role = await session.scalar(
                select(Role)
                .where(Role.key == ADMIN_ROLE_KEY)
                .options(selectinload(Role.permissions))
            )
            if role is None:
                raise SystemExit("The Admin role is missing: run the seeders first.")
            session.add(
                User(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=hash_password(password),
                    roles=[role],
                )
            )
            await session.commit()
    finally:
        await engine.dispose()
    return password


def main() -> None:
    if len(sys.argv) < 2 or "@" not in sys.argv[1]:
        raise SystemExit(__doc__)
    email = sys.argv[1].strip().lower()
    first = sys.argv[2] if len(sys.argv) > 2 else "Admin"
    last = sys.argv[3] if len(sys.argv) > 3 else "Admin"
    password = asyncio.run(create_admin(email, first, last))
    print(f"Administrator {email} created. Password (shown once): {password}")


if __name__ == "__main__":
    main()
