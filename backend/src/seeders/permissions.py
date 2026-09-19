from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.rbac.permission import Permission

USER_PERMISSIONS = (
    ("users.list", "List users", "View the list of users"),
    ("users.read", "Read user", "View a single user"),
    ("users.create", "Create user", "Create a new user"),
    ("users.update", "Update user", "Update an existing user"),
    ("users.delete", "Delete user", "Delete a user"),
)


async def seed_permissions(session: AsyncSession) -> None:
    existing = set(
        await session.scalars(select(Permission.key).where(Permission.key.like("users.%")))
    )
    session.add_all(
        [
            Permission(key=key, name=name, description=description)
            for key, name, description in USER_PERMISSIONS
            if key not in existing
        ]
    )
