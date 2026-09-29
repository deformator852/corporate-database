from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.document import DocumentClassification
from models.rbac import role_permissions, role_users
from models.rbac.permission import Permission

RESTRICTED_PERMISSION = "documents.restricted"
CONFIDENTIAL_PERMISSION = "documents.confidential"
SECRET_PERMISSION = "documents.secret"
RETRIEVE_PERMISSIONS = frozenset(
    {
        "documents.list",
        RESTRICTED_PERMISSION,
        CONFIDENTIAL_PERMISSION,
        SECRET_PERMISSION,
    }
)


def allowed_classifications(permission_keys: Iterable[str]) -> tuple[str, ...]:
    keys = set(permission_keys)
    allowed = [DocumentClassification.STANDARD.value]
    if (
        RESTRICTED_PERMISSION in keys
        or CONFIDENTIAL_PERMISSION in keys
        or SECRET_PERMISSION in keys
    ):
        allowed.append(DocumentClassification.RESTRICTED.value)
    if CONFIDENTIAL_PERMISSION in keys or SECRET_PERMISSION in keys:
        allowed.append(DocumentClassification.CONFIDENTIAL.value)
    if SECRET_PERMISSION in keys:
        allowed.append(DocumentClassification.SECRET.value)
    return tuple(allowed)


def retrieval_classifications(permission_keys: Iterable[str]) -> tuple[str, ...]:
    keys = set(permission_keys)
    if keys.isdisjoint(RETRIEVE_PERMISSIONS):
        return ()
    return allowed_classifications(keys)


async def user_permission_keys(session: AsyncSession, user_id: int) -> set[str]:
    keys = await session.scalars(
        select(Permission.key)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(role_users, role_users.c.role_id == role_permissions.c.role_id)
        .where(role_users.c.user_id == user_id)
    )
    return set(keys)


async def classifications_for_user(
    session: AsyncSession, user_id: int
) -> tuple[str, ...]:
    return allowed_classifications(await user_permission_keys(session, user_id))
