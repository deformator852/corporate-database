from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.rbac.constants import ADMIN_ROLE_KEY
from models.rbac.permission import Permission
from models.rbac.role import Role
from seeders.permissions import ALL_PERMISSIONS

CATALOG_KEYS = frozenset(key for key, _name, _description in ALL_PERMISSIONS)


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    name: str
    description: str
    # None: every permission of the catalog.
    permission_keys: list[str] | None


ROLE_DEFINITIONS = {
    ADMIN_ROLE_KEY: RoleDefinition(name="Admin", description="Full access", permission_keys=None),
}


async def seed_roles(session: AsyncSession) -> None:
    # Catalog only: a permission dropped from the catalog must not stay on the
    # admin role, or the permission seeder can never delete it.
    permissions = [
        permission for permission in await session.scalars(select(Permission)) if permission.key in CATALOG_KEYS
    ]
    permissions_by_key = {permission.key: permission for permission in permissions}
    roles = {
        role.key: role
        for role in await session.scalars(
            select(Role).options(selectinload(Role.permissions), selectinload(Role.users))
        )
    }

    for key, definition in ROLE_DEFINITIONS.items():
        assigned = _assigned_permissions(
            definition.permission_keys,
            permissions=permissions,
            permissions_by_key=permissions_by_key,
        )
        role = roles.get(key)
        if role is None:
            session.add(
                Role(
                    key=key,
                    name=definition.name,
                    description=definition.description,
                    permissions=assigned,
                )
            )
            continue
        role.name = definition.name
        role.description = definition.description
        role.permissions = assigned

    # Only the roles defined here are managed; roles created in the UI are
    # left alone, even with no users yet.
    await session.flush()


def _assigned_permissions(
    permission_keys: list[str] | None,
    *,
    permissions: list[Permission],
    permissions_by_key: dict[str, Permission],
) -> list[Permission]:
    if permission_keys is None:
        return list(permissions)
    return [
        permissions_by_key[permission_key] for permission_key in permission_keys if permission_key in permissions_by_key
    ]


if __name__ == "__main__":
    import asyncio

    from database import AsyncSessionLocal

    async def main() -> None:
        async with AsyncSessionLocal() as session:
            await seed_roles(session)
            await session.commit()

    asyncio.run(main())
