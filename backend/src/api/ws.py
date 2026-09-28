import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from authx.schema import TokenPayload
from fastapi import WebSocket, WebSocketDisconnect

from security import session_active

RECHECK_SECONDS = 60
# Client refreshes its session and reconnects on this code.
CLOSE_SESSION_ENDED = 4401
CLOSE_FORBIDDEN = 4403


def seconds_left(payload: TokenPayload) -> float:
    return (payload.expiry_datetime - datetime.now(UTC)).total_seconds()


async def still_allowed(websocket: WebSocket, payload: TokenPayload) -> int | None:
    """Close code if the socket must end now, else None."""
    if seconds_left(payload) <= 0:
        return CLOSE_SESSION_ENDED
    if not await session_active(payload, websocket.state.access_token):
        return CLOSE_SESSION_ENDED
    return None


async def hold(
    websocket: WebSocket,
    payload: TokenPayload,
    recheck: Callable[[], Awaitable[bool]] | None = None,
) -> None:
    """Keeps an accepted listen-only socket open until the client leaves, the
    access token expires or is revoked, or `recheck` (permissions) fails."""
    while True:
        timeout = max(0.0, min(RECHECK_SECONDS, seconds_left(payload)))
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
            continue
        except TimeoutError:
            pass
        except WebSocketDisconnect:
            return
        code = await still_allowed(websocket, payload)
        if code is None and recheck is not None and not await recheck():
            code = CLOSE_FORBIDDEN
        if code is not None:
            await websocket.close(code=code)
            return
