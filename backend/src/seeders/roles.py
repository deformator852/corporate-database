from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.permission import Permission
from models.rbac.role import Role

ROLE_DEFINITIONS = {
    ADMIN_ROLE_KEY: {
        "name": "Admin",
        "description": "Full access",
        "permission_keys": None,
    },
}


async def seed_roles(session: AsyncSession) -> None:
    permissions = list(await session.scalars(select(Permission)))
    permissions_by_key = {permission.key: permission for permission in permissions}
    roles = {
        role.key: role
        for role in await session.scalars(
            select(Role).options(selectinload(Role.permissions), selectinload(Role.users))
        )
    }

    for key, definition in ROLE_DEFINITIONS.items():
        assigned = _assigned_permissions(
            definition["permission_keys"],
            permissions=permissions,
            permissions_by_key=permissions_by_key,
        )
        role = roles.get(key)
        if role is None:
            session.add(
                Role(
                    key=key,
                    name=definition["name"],
                    description=definition["description"],
                    permissions=assigned,
                )
            )
            continue
        role.name = definition["name"]
        role.description = definition["description"]
        role.permissions = assigned

    await session.flush()
    await _delete_unassigned_roles(session)


def _assigned_permissions(
    permission_keys: list[str] | None,
    *,
    permissions: list[Permission],
    permissions_by_key: dict[str, Permission],
) -> list[Permission]:
    if permission_keys is None:
        return list(permissions)
    return [
        permissions_by_key[permission_key]
        for permission_key in permission_keys
        if permission_key in permissions_by_key
    ]


async def _delete_unassigned_roles(session: AsyncSession) -> None:
    kept_keys = set(ROLE_DEFINITIONS)
    extras = await session.scalars(
        select(Role)
        .where(Role.key.not_in(kept_keys))
        .options(selectinload(Role.users))
    )
    for role in extras:
        if role.key == ADMIN_ROLE_KEY or role.users:
            continue
        await session.delete(role)
