from authx.schema import TokenPayload
from fastapi import APIRouter, Depends, Response

from api.deps import get_auth_service
from schemas.error_schema import ErrorSchema
from schemas.login import UserLoginSchema
from schemas.login.user_login_response_schema import UserLoginResponseSchema
from security import security, set_auth_cookies
from services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/login",
    response_model=UserLoginResponseSchema,
    responses={401: {"model": ErrorSchema}},
)
async def login(
    creds: UserLoginSchema,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> UserLoginResponseSchema:
    user = await auth.authenticate(creds.email, creds.password)
    set_auth_cookies(response, str(user.id), fresh=True)
    return UserLoginResponseSchema(email=user.email)


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
