import hashlib
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from authx import AuthX, AuthXConfig
from authx.schema import RequestToken, TokenPayload
from dotenv import load_dotenv
from fastapi import Cookie, WebSocket
from sqlalchemy import delete
from starlette.responses import Response

from database import AsyncSessionLocal
from exceptions import AppError
from models.revoked_token import RevokedToken
from models.user import User

load_dotenv()

ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRES = timedelta(hours=8)

config = AuthXConfig()
config.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
config.JWT_TOKEN_LOCATION = ["cookies"]
config.JWT_ACCESS_COOKIE_NAME = "my_token"
config.JWT_REFRESH_COOKIE_NAME = "my_refresh"
config.JWT_ACCESS_TOKEN_EXPIRES = ACCESS_TOKEN_EXPIRES
config.JWT_REFRESH_TOKEN_EXPIRES = REFRESH_TOKEN_EXPIRES

security = AuthX(config)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def is_token_revoked(token: str, **_: object) -> bool:
    async with AsyncSessionLocal() as session:
        found = await session.get(RevokedToken, _token_hash(token))
    return found is not None


security.set_callback_token_blocklist(is_token_revoked)


async def revoke_tokens(*tokens: str | None) -> None:
    """Blocks the given encoded tokens until they would have expired anyway."""
    now = datetime.now(UTC)
    # Upper bound for both kinds; rows are dropped once past it.
    expires_at = now + REFRESH_TOKEN_EXPIRES
    async with AsyncSessionLocal() as session:
        await session.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
        for token in {token for token in tokens if token}:
            await session.merge(RevokedToken(token_hash=_token_hash(token), expires_at=expires_at))
        await session.commit()


def sessions_cutoff() -> datetime:
    """Value for users.sessions_valid_after that ends every current session.
    Token issue times have 1-second precision, so round up: a token issued
    earlier in this same second is revoked too (a new sign-in waits <1 s)."""
    return datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=1)


def user_session_valid(user: User | None, payload: TokenPayload) -> bool:
    """False for deleted or disabled users and tokens issued before a
    password change."""
    if user is None or user.is_disabled:
        return False
    if user.sessions_valid_after is None:
        return True
    return payload.issued_at >= user.sessions_valid_after


async def session_active(payload: TokenPayload, token: str) -> bool:
    if await is_token_revoked(token):
        return False
    try:
        user_id = int(payload.sub)
    except TypeError, ValueError:
        return False
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
    return user_session_valid(user, payload)


ACCESS_COOKIE_MAX_AGE = int(ACCESS_TOKEN_EXPIRES.total_seconds())
REFRESH_COOKIE_MAX_AGE = int(REFRESH_TOKEN_EXPIRES.total_seconds())


def set_auth_cookies(response: Response, uid: str, *, fresh: bool) -> None:
    access_token = security.create_access_token(uid=uid, fresh=fresh)
    refresh_token = security.create_refresh_token(uid=uid)
    security.set_access_cookies(access_token, response, max_age=ACCESS_COOKIE_MAX_AGE)
    security.set_refresh_cookies(refresh_token, response, max_age=REFRESH_COOKIE_MAX_AGE)


def _same_origin(websocket: WebSocket) -> bool:
    # Browsers always send Origin on WebSocket handshakes; a cross-site page
    # must not ride the user's cookies. Non-browser clients send none.
    origin = websocket.headers.get("origin")
    if origin is None:
        return True
    return urlsplit(origin).netloc == websocket.headers.get("host")


async def get_ws_payload(
    websocket: WebSocket,
    my_token: str | None = Cookie(default=None),
) -> TokenPayload:
    if not _same_origin(websocket):
        raise AppError("forbidden", "Cross-origin socket", status_code=403)
    token = my_token or websocket.cookies.get(config.JWT_ACCESS_COOKIE_NAME)
    if not token:
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    request_token = RequestToken(
        token=token,
        csrf=None,
        type="access",
        location="cookies",
    )
    try:
        payload = security.verify_token(
            request_token,
            verify_type=True,
            verify_fresh=False,
            verify_csrf=False,
        )
    except Exception as exc:
        raise AppError("unauthorized", "Not authenticated", status_code=401) from exc
    if not await session_active(payload, token):
        raise AppError("unauthorized", "Not authenticated", status_code=401)
    # Kept for periodic re-checks while the socket stays open.
    websocket.state.access_token = token
    return payload
