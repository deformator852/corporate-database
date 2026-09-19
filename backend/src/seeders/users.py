from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.role import Role
from models.user import User
from services.password import hash_password

SEED_PASSWORD = "password"


async def seed_users(session: AsyncSession) -> None:
    exists = await session.scalar(select(User.id).limit(1))
    if exists is None:
        session.add_all(
            [
                User(
                    first_name="John",
                    last_name="Doe",
                    email="admin@local.test",
                    password=hash_password(SEED_PASSWORD),
                ),
                User(
                    first_name="Michael",
                    last_name="Keel",
                    email="dev@local.test",
                    password=hash_password(SEED_PASSWORD),
                ),
            ]
        )
        await session.flush()

    admin_role = await session.scalar(select(Role).where(Role.key == "admin"))
    admin_user = await session.scalar(
        select(User)
        .where(User.email == "admin@local.test")
        .options(selectinload(User.roles))
    )
    if admin_role is None or admin_user is None:
        return
    if admin_role not in admin_user.roles:
        admin_user.roles.append(admin_role)

