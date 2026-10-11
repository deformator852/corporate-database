from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from extensions import plugins
from models.rbac.association import role_permissions
from models.rbac.permission import Permission

USER_PERMISSIONS = (
    ("users.list", "List users", "View the list of users"),
    (
        "users.view",
        "View user",
        "Open a user's page: profile and history of their actions",
    ),
    ("users.create", "Create user", "Create a new user"),
    ("users.update", "Update user", "Update an existing user"),
    (
        "users.disable",
        "Disable user",
        "Block or allow a user's sign-in; the account and its history stay",
    ),
    ("users.delete", "Delete user", "Delete a user"),
)

ROLE_PERMISSIONS = (
    ("roles.list", "List roles", "View the list of roles"),
    ("roles.create", "Create role", "Create a new role"),
    ("roles.update", "Update role", "Update an existing role"),
    ("roles.delete", "Delete role", "Delete a role"),
)

PERMISSION_PERMISSIONS = (("permissions.list", "List permissions", "View the list of permissions"),)

DOCUMENT_PERMISSIONS = (
    ("documents.list", "List documents", "View the list of documents"),
    ("documents.create", "Create document", "Upload a new document or process a failed one again"),
    ("documents.update", "Update document", "Rename a document or change its access level"),
    ("documents.delete", "Delete document", "Delete a document"),
    (
        "documents.restricted",
        "Restricted documents",
        "Access restricted documents and their search results",
    ),
    (
        "documents.confidential",
        "Confidential documents",
        "Access confidential documents and their search results",
    ),
    (
        "documents.secret",
        "Secret documents",
        "Access secret documents and their search results",
    ),
)

CHAT_PERMISSIONS = (
    (
        "chat.feedback",
        "View answer ratings",
        "See answers users rated, with their questions, to find where the assistant goes wrong",
    ),
    (
        "chat.history",
        "View chat history",
        "Read the saved chats of users with no more access than yours",
    ),
    (
        "chat.purge",
        "Clear chat history",
        "Delete saved chats of users with no more access than yours, all or for a period",
    ),
)

AUDIT_PERMISSIONS = (
    (
        "audit.list",
        "View audit log",
        "View who signed in and changed users, roles and documents",
    ),
)

SYSTEM_PERMISSIONS = (
    (
        "system.view",
        "View system status",
        "See whether the database, search, storage, queue and AI models work",
    ),
    (
        "system.errors",
        "View error log",
        "See the warnings and errors of the backend and the worker, with their tracebacks",
    ),
    (
        "system.rechunk",
        "Update documents for search",
        "Prepare documents again for search after the search settings change (System page)",
    ),
)

ALL_PERMISSIONS = (
    USER_PERMISSIONS
    + ROLE_PERMISSIONS
    + PERMISSION_PERMISSIONS
    + DOCUMENT_PERMISSIONS
    + CHAT_PERMISSIONS
    + AUDIT_PERMISSIONS
    + SYSTEM_PERMISSIONS
    + tuple(permission for plugin in plugins() for permission in getattr(plugin, "PERMISSIONS", ()))
)


async def seed_permissions(session: AsyncSession) -> None:
    wanted = {key: (name, description) for key, name, description in ALL_PERMISSIONS}
    existing = {permission.key: permission for permission in await session.scalars(select(Permission))}

    for key, (name, description) in wanted.items():
        permission = existing.get(key)
        if permission is None:
            session.add(Permission(key=key, name=name, description=description))
            continue
        permission.name = name
        permission.description = description

    await session.flush()
    await _delete_unused_permissions(session, wanted_keys=set(wanted))


async def _delete_unused_permissions(session: AsyncSession, *, wanted_keys: set[str]) -> None:
    assigned_ids = set(await session.scalars(select(role_permissions.c.permission_id)))
    leftovers = await session.scalars(select(Permission).where(Permission.key.not_in(wanted_keys)))
    for permission in leftovers:
        if permission.id in assigned_ids:
            continue
        await session.delete(permission)
    await session.flush()


if __name__ == "__main__":
    import asyncio

    from database import AsyncSessionLocal

    async def main() -> None:
        async with AsyncSessionLocal() as session:
            await seed_permissions(session)
            await session.commit()

    asyncio.run(main())
