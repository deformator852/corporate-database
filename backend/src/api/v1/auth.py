from authx.schema import TokenPayload
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from api.deps import get_audit_service, get_auth_service, get_current_user
from exceptions import AppError
from i18n import use_language
from models.audit import AuditAction
from models.user import User
from schemas.auth import LanguageSchema, LoginSchema, PasswordChangeSchema, SessionUserSchema
from schemas.error import error_responses
from security import config, revoke_tokens, security, session_expired, set_auth_cookies, signed_in_at
from services import sso
from services.audit import AuditService
from services.auth import AuthService
from settings import languages, oidc_config

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
    if user is None or session_expired(payload):
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    # Rotation: each refresh token works once.
    await revoke_tokens(request.cookies.get(config.JWT_REFRESH_COOKIE_NAME))
    set_auth_cookies(response, str(user.id), fresh=False, since=signed_in_at(payload))


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


@router.get("/methods")
async def sign_in_methods() -> dict[str, object]:
    """What the sign-in page offers. Public: it shows before sign-in."""
    oidc = oidc_config()
    return {
        # With single sign-on, only administrators sign in with a Corpus
        # password, behind a link on the page.
        "password": oidc is None,
        "sso": {"name": oidc.name} if oidc else None,
    }


@router.get("/sso/start", responses=error_responses(404, 503))
async def sso_start() -> RedirectResponse:
    """Sends the browser to the company's sign-in page."""
    oidc = oidc_config()
    if oidc is None:
        raise AppError("not_found", "Single sign-on is not set up.", status_code=404)
    url, cookie = await sso.start(oidc, _state_secret())
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        sso.STATE_COOKIE,
        cookie,
        max_age=sso.STATE_SECONDS,
        path=sso.STATE_COOKIE_PATH,
        secure=True,
        httponly=True,
        # Lax: the provider sends the browser back with a top-level GET.
        samesite="lax",
    )
    return response


@router.get("/sso/callback")
async def sso_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    auth: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """The provider sends the browser back here. Signs in and opens the app;
    on a problem, opens the sign-in page with its code (never the provider's
    text)."""
    oidc = oidc_config()
    try:
        if oidc is None:
            raise AppError("not_found", "Single sign-on is not set up.", status_code=404)
        if error or not code:
            raise AppError("sso_denied", "The sign-in was cancelled.", status_code=400)
        identity = await sso.finish(
            oidc, _state_secret(), code=code, state=state, cookie=request.cookies.get(sso.STATE_COOKIE)
        )
        user = await auth.sso_login(identity, oidc)
        response = RedirectResponse("/", status_code=302)
        set_auth_cookies(response, str(user.id), fresh=True)
    except AppError as exc:
        response = RedirectResponse(f"/login?sso_error={exc.code}", status_code=302)
    response.delete_cookie(sso.STATE_COOKIE, path=sso.STATE_COOKIE_PATH, secure=True, httponly=True, samesite="lax")
    return response


def _state_secret() -> str:
    """Signs the sign-in state cookie: the same key as the session tokens."""
    return str(config.JWT_SECRET_KEY)
