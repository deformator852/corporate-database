from typing import Self

from pydantic import BaseModel, ConfigDict

from models.rbac.permission import Permission


class RoleRefSchema(BaseModel):
    key: str
    name: str


class PermissionListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
                (
                    RoleRefSchema(key=role.key, name=role.name)
                    for role in permission.roles
                ),
                key=lambda item: item.key,
            ),
        )


class PermissionListResponseSchema(BaseModel):
    items: list[PermissionListItemSchema]
    page: int
    per_page: int
    total: int
    pages: int

    @classmethod
    def from_page(
        cls,
        permissions: list[Permission],
        *,
        page: int,
        per_page: int,
        total: int,
    ) -> Self:
        pages = (total + per_page - 1) // per_page if per_page and total else 0
        return cls(
            items=[
                PermissionListItemSchema.from_permission(permission)
                for permission in permissions
            ],
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
        )
