import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from authx.exceptions import AuthXException, CSRFError, MissingCSRFTokenError
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

load_dotenv()

from api.v1.router import api_router
from database import AsyncSessionLocal
from exceptions import AppError
from extensions import plugins
from i18n import t, use_language
from schemas.error import ErrorSchema, validation_message
from security import SocketRefused, check_jwt_secret
from services import error_log
from services.chat.generator import OllamaGenerator
from services.chat.history import ChatHistoryService
from services.chat.limit import close_open_chat_requests, purge_chat_requests
from services.documents.events import consume_document_events
from services.documents.file_check import mark_missing_files
from services.documents.hub import hub
from services.encryption_key import verify_encryption_key
from services.error_log import ErrorLogService
from services.notifications.events import consume_notification_events
from services.notifications.hub import dispatch_notification
from services.search.embedding import get_embedding_model
from services.search.index_model import record_index_model
from services.search.reindex_hub import reindex_hub
from services.storage import file_store
from settings import chat_retention_days, error_log_retention_days

logger = logging.getLogger(__name__)


async def warm_up() -> None:
    """Loads the embedding model and the LLM in the background, so the first
    question after a restart does not wait for them."""
    try:
        await asyncio.to_thread(get_embedding_model().warm_up)
    except Exception:
        logger.warning("Embedding model warm-up failed", exc_info=True)
    try:
        await OllamaGenerator().warm_up()
    except Exception:
        logger.warning("LLM warm-up failed", exc_info=True)


async def check_files() -> None:
    """Marks the documents whose file is missing from the storage, which
    changes only with a restart. In the background: one request per file."""
    try:
        async with AsyncSessionLocal() as session:
            await mark_missing_files(session, file_store())
    except Exception:
        logger.warning("Document file check failed", exc_info=True)


_PURGE_EVERY_SECONDS = 6 * 3600


async def purge_old_chats() -> None:
    """Every 6 hours: deletes saved chats idle longer than CHAT_RETENTION_DAYS,
    chat limit records older than a day and error log entries older than
    ERROR_LOG_RETENTION_DAYS."""
    while True:
        try:
            days = chat_retention_days()
            if days:
                async with AsyncSessionLocal() as session:
                    removed = await ChatHistoryService(session).purge_older_than(days)
                if removed:
                    logger.info("Deleted %s chat(s) older than %s days", removed, days)
            await purge_chat_requests()
            if error_days := error_log_retention_days():
                async with AsyncSessionLocal() as session:
                    await ErrorLogService(session).purge_older_than(error_days)
        except Exception:
            logger.warning("Chat retention cleanup failed", exc_info=True)
        await asyncio.sleep(_PURGE_EVERY_SECONDS)


_RESTART_SECONDS = 5


async def keep_running(name: str, consume: Callable[[], Awaitable[None]]) -> None:
    """Runs a consumer again whenever it stops: RabbitMQ down at start or
    restarted later would otherwise end live updates until a restart."""
    while True:
        try:
            await consume()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("%s stopped; restarting in %s s", name, _RESTART_SECONDS, exc_info=True)
        await asyncio.sleep(_RESTART_SECONDS)


async def on_document_event(payload: dict) -> None:
    """A document moved on: the documents lists, and the model switch banner."""
    await hub.broadcast(payload)
    await reindex_hub.refresh()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # First: a failed start is worth an entry too.
    error_log.install("backend")
    check_jwt_secret()
    # Fail fast: with the wrong key, new data would be unreadable later.
    async with AsyncSessionLocal() as session:
        await verify_encryption_key(session)
        await record_index_model(session)
    await close_open_chat_requests()
    warm_up_task = asyncio.create_task(warm_up())
    files_task = asyncio.create_task(check_files())
    purge_task = asyncio.create_task(purge_old_chats())
    document_task = asyncio.create_task(
        keep_running("Document events", lambda: consume_document_events(on_document_event))
    )
    notification_task = asyncio.create_task(
        keep_running("Notification events", lambda: consume_notification_events(dispatch_notification))
    )
    try:
        yield
    finally:
        tasks = (warm_up_task, files_task, purge_task, document_task, notification_task)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


# The schema maps every endpoint; only expose it where you develop.
_DOCS = (os.getenv("API_DOCS") or "").strip().lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Corpus",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)

# JSON API only: nothing here should render as a page or sit in a frame.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


@app.middleware("http")
async def request_language(request: Request, call_next):
    """The client's interface language (sent as Accept-Language); a signed-in
    user's saved choice replaces it (`get_current_user`)."""
    first = request.headers.get("accept-language", "").split(",")[0].split(";")[0]
    use_language(first.split("-")[0].strip().lower() or None)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if not _DOCS:
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


class SocketErrors:
    """Exception handlers cover HTTP requests only: a socket's error would
    reach the log as uvicorn's "Exception in ASGI application". Logged here
    with the socket's path instead, and marked so uvicorn's copy is skipped.
    Refusals (no session, no permission) are not errors."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except SocketRefused:
            return  # closed with its code already: a refusal, not an error
        except Exception as exc:
            refused = isinstance(exc, AppError) and exc.status_code < 500
            if not refused and not getattr(exc, error_log.LOGGED, False):
                # The path, not the query string, as for requests.
                logger.error(
                    "Unhandled error on socket %s", scope.get("path"), exc_info=exc, extra={"category": "unhandled"}
                )
                setattr(exc, error_log.LOGGED, True)
            raise


app.add_middleware(SocketErrors)
app.include_router(api_router)
for plugin in plugins():
    if hasattr(plugin, "setup"):
        plugin.setup(app)


# Every authx error in the common `{code, message}` shape. A handler for the
# base class also stops authx from installing its own (other shapes, and 422
# for a bad signature, while clients sign in again only on 401).
@app.exception_handler(AuthXException)
async def auth_error_handler(_request: Request, exc: AuthXException) -> JSONResponse:
    # authx re-raises a missing CSRF header as a plain MissingTokenError, so
    # the message is the only sign left.
    if isinstance(exc, (CSRFError, MissingCSRFTokenError)) or "CSRF token" in str(exc):
        # The session is fine; the request is not. 401 would sign the user out.
        body = ErrorSchema(code="forbidden", message=t("The request has no valid security token. Reload the page."))
        return JSONResponse(status_code=403, content=body.model_dump())
    body = ErrorSchema(code="unauthorized", message=t("Not authenticated"))
    return JSONResponse(status_code=401, content=body.model_dump())


# Same `{code, message}` as every other error, so forms can show it.
@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    body = ErrorSchema(code="invalid", message=t(validation_message(list(exc.errors()))))
    return JSONResponse(status_code=400, content=body.model_dump())


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    body = ErrorSchema(code=exc.code, message=t(exc.message, **exc.params))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


# A bug: the error log gets the traceback, the client the common error shape.
@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # The path, not the query string: it may hold search text.
    logger.error(
        "Unhandled error on %s %s", request.method, request.url.path, exc_info=exc, extra={"category": "unhandled"}
    )
    # Starlette re-raises it for the server, and uvicorn logs it again.
    setattr(exc, error_log.LOGGED, True)
    body = ErrorSchema(code="internal", message=t("Something went wrong. Try again."))
    return JSONResponse(status_code=500, content=body.model_dump())


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
