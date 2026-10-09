from authx.schema import TokenPayload
from fastapi import APIRouter, Depends, Request, Response

from api.deps import get_audit_service, get_auth_service, get_current_user
from exceptions import AppError
from i18n import use_language
from models.audit import AuditAction
from models.user import User
from schemas.auth import LanguageSchema, LoginSchema, PasswordChangeSchema, SessionUserSchema
from schemas.error import error_responses
from security import config, revoke_tokens, security, set_auth_cookies
from services.audit import AuditService
from services.auth import AuthService
from settings import languages

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/login",
    response_model=SessionUserSchema,
    responses=error_responses(401, 429),
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
    responses=error_responses(401),
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
    responses=error_responses(401),
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


@router.post(
    "/password",
    status_code=204,
    responses=error_responses(400, 401, 429),
)
async def change_password(
    payload: PasswordChangeSchema,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    """The user's own password. Every session ends, this one too."""
    await auth.change_password(user, payload)
    await revoke_tokens(
        request.cookies.get(config.JWT_ACCESS_COOKIE_NAME),
        request.cookies.get(config.JWT_REFRESH_COOKIE_NAME),
    )
    security.unset_cookies(response)


@router.get(
    "/me",
    response_model=SessionUserSchema,
    responses=error_responses(401),
)
async def me(
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> SessionUserSchema:
    loaded = await auth.get_with_permissions(user.id)
    if loaded is None:
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    return SessionUserSchema.from_user(loaded)


@router.put(
    "/language",
    status_code=204,
    responses=error_responses(400, 401),
)
async def set_language(
    payload: LanguageSchema,
    user: User = Depends(get_current_user),
) -> None:
    """The user's own interface language: answers, errors and notices
    follow it."""
    if payload.language not in languages():
        raise AppError("invalid", "This language is not available.", status_code=400)
    user.language = payload.language
    use_language(user.language)
