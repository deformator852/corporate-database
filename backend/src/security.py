import os
from datetime import timedelta

from authx import AuthX, AuthXConfig
from authx.schema import RequestToken, TokenPayload
from dotenv import load_dotenv
from fastapi import Cookie, WebSocket
from starlette.responses import Response

from exceptions import AppError

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

ACCESS_COOKIE_MAX_AGE = int(ACCESS_TOKEN_EXPIRES.total_seconds())
REFRESH_COOKIE_MAX_AGE = int(REFRESH_TOKEN_EXPIRES.total_seconds())


def set_auth_cookies(response: Response, uid: str, *, fresh: bool) -> None:
    access_token = security.create_access_token(uid=uid, fresh=fresh)
    refresh_token = security.create_refresh_token(uid=uid)
    security.set_access_cookies(access_token, response, max_age=ACCESS_COOKIE_MAX_AGE)
    security.set_refresh_cookies(refresh_token, response, max_age=REFRESH_COOKIE_MAX_AGE)


async def get_ws_payload(
    websocket: WebSocket,
    my_token: str | None = Cookie(default=None),
) -> TokenPayload:
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
        return security.verify_token(
            request_token,
            verify_type=True,
            verify_fresh=False,
            verify_csrf=False,
        )
    except Exception as exc:
        raise AppError("unauthorized", "Not authenticated", status_code=401) from exc
