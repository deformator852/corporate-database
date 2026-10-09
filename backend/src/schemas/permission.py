from typing import Self

from pydantic import BaseModel

from models.rbac.permission import Permission
from schemas.model_config import ORM_MODEL_CONFIG
from schemas.page import PageSchema
from schemas.role import RoleRefSchema


class PermissionListItemSchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    key: str
    name: str
    description: str
    roles: list[RoleRefSchema]

    @classmethod
    def from_permission(cls, permission: Permission) -> Self:
        return cls(
            key=permission.key,
            name=permission.name,
            description=permission.description,
            roles=sorted(
                (RoleRefSchema(key=role.key, name=role.name) for role in permission.roles),
                key=lambda item: item.key,
            ),
        )


class PermissionListResponseSchema(PageSchema):
    items: list[PermissionListItemSchema]

    @classmethod
    def from_page(
        cls,
        permissions: list[Permission],
        *,
        page: int,
        per_page: int,
        total: int,
    ) -> Self:
        return cls(
            items=[PermissionListItemSchema.from_permission(permission) for permission in permissions],
            page=page,
            per_page=per_page,
            total=total,
        )
