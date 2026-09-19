from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.permission import Permission
from models.rbac.role import Role


async def seed_roles(session: AsyncSession) -> None:
    user_permissions = list(
        await session.scalars(
            select(Permission).where(Permission.key.like("users.%"))
        )
    )
    admin = await session.scalar(
        select(Role)
        .where(Role.key == "admin")
        .options(selectinload(Role.permissions))
    )
    if admin is None:
        admin = Role(
            key="admin",
            name="Admin",
            description="Full access",
            permissions=user_permissions,
        )
        session.add(admin)
        return

    have = {permission.key for permission in admin.permissions}
    for permission in user_permissions:
        if permission.key not in have:
            admin.permissions.append(permission)
