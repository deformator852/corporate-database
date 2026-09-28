from authx.schema import TokenPayload
from fastapi import APIRouter, Depends, Request, Response

from api.deps import get_audit_service, get_auth_service, get_current_user
from exceptions import AppError
from models.audit import AuditAction
from models.user import User
from schemas.auth import LoginSchema, SessionUserSchema
from schemas.error import ErrorSchema
from security import config, revoke_tokens, security, set_auth_cookies
from services.audit import AuditService
from services.auth import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/login",
    response_model=SessionUserSchema,
    responses={401: {"model": ErrorSchema}, 429: {"model": ErrorSchema}},
)
async def login(
    creds: LoginSchema,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
) -> SessionUserSchema:
    user = await auth.login(creds)
    set_auth_cookies(response, str(user.id), fresh=True)
    return SessionUserSchema.from_user(user)


@router.post(
    "/refresh",
    status_code=204,
    responses={401: {"model": ErrorSchema}},
)
async def refresh(
    request: Request,
    response: Response,
    payload: TokenPayload = Depends(security.refresh_token_required),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    user = await auth.session_user(payload)
    if user is None:
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    # Rotation: each refresh token works once.
    await revoke_tokens(request.cookies.get(config.JWT_REFRESH_COOKIE_NAME))
    set_auth_cookies(response, str(user.id), fresh=False)


@router.post(
    "/logout",
    status_code=204,
    responses={401: {"model": ErrorSchema}},
)
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> None:
    await revoke_tokens(
        request.cookies.get(config.JWT_ACCESS_COOKIE_NAME),
        request.cookies.get(config.JWT_REFRESH_COOKIE_NAME),
    )
    security.unset_cookies(response)
    audit.record(AuditAction.LOGOUT, actor=user)


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
