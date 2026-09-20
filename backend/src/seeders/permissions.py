from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.rbac.association import role_permissions
from models.rbac.permission import Permission

USER_PERMISSIONS = (
    ("users.list", "List users", "View the list of users"),
    ("users.create", "Create user", "Create a new user"),
    ("users.update", "Update user", "Update an existing user"),
    ("users.delete", "Delete user", "Delete a user"),
)

ROLE_PERMISSIONS = (
    ("roles.list", "List roles", "View the list of roles"),
    ("roles.create", "Create role", "Create a new role"),
    ("roles.update", "Update role", "Update an existing role"),
    ("roles.delete", "Delete role", "Delete a role"),
)

PERMISSION_PERMISSIONS = (
    ("permissions.list", "List permissions", "View the list of permissions"),
)

ALL_PERMISSIONS = USER_PERMISSIONS + ROLE_PERMISSIONS + PERMISSION_PERMISSIONS


async def seed_permissions(session: AsyncSession) -> None:
    wanted = {key: (name, description) for key, name, description in ALL_PERMISSIONS}
    existing = {
        permission.key: permission
        for permission in await session.scalars(select(Permission))
    }

    for key, (name, description) in wanted.items():
        permission = existing.get(key)
        if permission is None:
            session.add(Permission(key=key, name=name, description=description))
            continue
        permission.name = name
        permission.description = description

    await session.flush()
    await _delete_unused_permissions(session, wanted_keys=set(wanted))


async def _delete_unused_permissions(
    session: AsyncSession, *, wanted_keys: set[str]
) -> None:
    assigned_ids = set(await session.scalars(select(role_permissions.c.permission_id)))
    leftovers = await session.scalars(
        select(Permission).where(Permission.key.not_in(wanted_keys))
    )
    for permission in leftovers:
        if permission.id in assigned_ids:
            continue
        await session.delete(permission)
    await session.flush()
