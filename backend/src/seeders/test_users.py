from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.role import Role
from models.user import User
from services.password import hash_password

ADMIN_EMAIL = "admin@local.test"


async def seed_test_users(session: AsyncSession) -> None:
    if await session.scalar(select(User.id).limit(1)) is None:
        session.add(
            User(
                first_name="Admin",
                last_name="Admin",
                email=ADMIN_EMAIL,
                password=hash_password("password"),
            )
        )
        await session.flush()

    admin_role = await session.scalar(select(Role).where(Role.key == ADMIN_ROLE_KEY))
    admin_user = await session.scalar(select(User).where(User.email == ADMIN_EMAIL).options(selectinload(User.roles)))
    if admin_role is None or admin_user is None:
        return
    if admin_role not in admin_user.roles:
        admin_user.roles.append(admin_role)


if __name__ == "__main__":
    import asyncio

    from database import AsyncSessionLocal

    async def main() -> None:
        async with AsyncSessionLocal() as session:
            await seed_test_users(session)
            await session.commit()

    asyncio.run(main())
