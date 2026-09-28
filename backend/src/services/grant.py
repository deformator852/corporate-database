from collections.abc import Iterable

from exceptions import AppError
from models.rbac.role import Role

# Holding users.update or roles.update must not be a path to admin: an actor
# may only hand out, and only manage holders of, permissions they have.


def role_keys(roles: Iterable[Role]) -> set[str]:
    return {permission.key for role in roles for permission in role.permissions}


def ensure_can_grant(actor_keys: set[str], keys: Iterable[str]) -> None:
    if not set(keys) <= actor_keys:
        raise AppError(
            "forbidden",
            "You cannot grant permissions you do not have",
            status_code=403,
        )


def ensure_can_manage(actor_keys: set[str], keys: Iterable[str]) -> None:
    if not set(keys) <= actor_keys:
        raise AppError(
            "forbidden",
            "You cannot change an account or role with more access than yours",
            status_code=403,
        )
