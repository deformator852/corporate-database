from authx.schema import TokenPayload
from fastapi import APIRouter, Depends, Response

from api.deps import get_auth_service, get_current_user
from exceptions import AppError
from models.user import User
from schemas.auth import LoginSchema, SessionUserSchema
from schemas.error import ErrorSchema
from security import security, set_auth_cookies
from services.auth import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/login",
    response_model=SessionUserSchema,
    responses={401: {"model": ErrorSchema}},
)
async def login(
    creds: LoginSchema,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> SessionUserSchema:
    user = await auth.authenticate(creds)
    set_auth_cookies(response, str(user.id), fresh=True)
    return SessionUserSchema.from_user(user)


@router.post(
    "/refresh",
    status_code=204,
    responses={401: {"model": ErrorSchema}},
)
async def refresh(
    response: Response,
    payload: TokenPayload = Depends(security.refresh_token_required),
) -> None:
    set_auth_cookies(response, payload.sub, fresh=False)


@router.get(
    "/me",
    response_model=SessionUserSchema,
    responses={401: {"model": ErrorSchema}},
)
async def me(
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> SessionUserSchema:
    loaded = await auth.get_with_permissions(user.id)
    if loaded is None:
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    return SessionUserSchema.from_user(loaded)
