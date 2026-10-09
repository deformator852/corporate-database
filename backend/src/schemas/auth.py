from typing import Self

from pydantic import BaseModel, Field, field_validator

from models.user import User
from schemas.email import Email
from schemas.model_config import MODEL_CONFIG, ORM_MODEL_CONFIG
from schemas.user import check_password_fits


class LoginSchema(BaseModel):
    model_config = MODEL_CONFIG

    email: Email
    password: str


class PasswordChangeSchema(BaseModel):
    """A user changing their own password."""

    model_config = MODEL_CONFIG

    current_password: str = Field(max_length=100)
    new_password: str = Field(min_length=8, max_length=100)

    _fits = field_validator("new_password")(check_password_fits)


class LanguageSchema(BaseModel):
    """The user's interface language, one of APP_LANGUAGES."""

    model_config = MODEL_CONFIG

    language: str = Field(max_length=8)


class SessionUserSchema(BaseModel):
    model_config = ORM_MODEL_CONFIG

    id: int
    first_name: str
    last_name: str
    email: Email
    permissions: list[str]
    # None until the user picks one in the header: the default language.
    language: str | None

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            language=user.language,
            permissions=sorted({permission.key for role in user.roles for permission in role.permissions}),
        )
