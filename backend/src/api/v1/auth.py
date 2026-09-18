from authx.schema import TokenPayload
from fastapi import APIRouter, Depends, Response

from api.deps import get_auth_service, get_current_user
from models.user import User
from schemas.auth import UserLoginResponseSchema, UserLoginSchema
from schemas.error_schema import ErrorSchema
from security import security, set_auth_cookies
from services.auth import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/auth",
    response_model=UserLoginResponseSchema,
    responses={401: {"model": ErrorSchema}},
)
async def login(
    creds: UserLoginSchema,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> User:
    user = await auth.authenticate(creds)
    set_auth_cookies(response, str(user.id), fresh=True)
    return user


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
    response_model=UserLoginResponseSchema,
    responses={401: {"model": ErrorSchema}},
)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
