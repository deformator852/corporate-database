import asyncio
import logging
import os
from contextlib import asynccontextmanager

from authx.exceptions import AuthXException, CSRFError, MissingCSRFTokenError
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

load_dotenv()

from api.v1.router import api_router
from exceptions import AppError
from i18n import t
from extensions import plugins
from schemas.error import ErrorSchema, validation_message
from services.documents.events import consume_document_events
from services.documents.hub import hub
from database import AsyncSessionLocal
from services.chat_history import ChatHistoryService
from services.embedding import get_embedding_model
from services.encryption_key import verify_encryption_key
from services.chat_limit import close_open_chat_requests, purge_chat_requests
from settings import chat_retention_days
from services.generator import OllamaGenerator
from services.notifications.events import consume_notification_events
from services.notifications.hub import dispatch_notification


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


_PURGE_EVERY_SECONDS = 6 * 3600


async def purge_old_chats() -> None:
    """Every 6 hours: deletes saved chats idle longer than CHAT_RETENTION_DAYS
    and chat limit records older than a day."""
    while True:
        try:
            days = chat_retention_days()
            if days:
                async with AsyncSessionLocal() as session:
                    removed = await ChatHistoryService(session).purge_older_than(days)
                if removed:
                    logger.info("Deleted %s chat(s) older than %s days", removed, days)
            await purge_chat_requests()
        except Exception:
            logger.warning("Chat retention cleanup failed", exc_info=True)
        await asyncio.sleep(_PURGE_EVERY_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Fail fast: with the wrong key, new data would be unreadable later.
    async with AsyncSessionLocal() as session:
        await verify_encryption_key(session)
    await close_open_chat_requests()
    warm_up_task = asyncio.create_task(warm_up())
    purge_task = asyncio.create_task(purge_old_chats())
    document_task = asyncio.create_task(consume_document_events(hub.broadcast))
    notification_task = asyncio.create_task(
        consume_notification_events(dispatch_notification)
    )
    try:
        yield
    finally:
        for task in (warm_up_task, purge_task, document_task, notification_task):
            task.cancel()
        for task in (warm_up_task, purge_task, document_task, notification_task):
            try:
                await task
            except asyncio.CancelledError:
                pass


# The schema maps every endpoint; only expose it where you develop.
_DOCS = (os.getenv("API_DOCS") or "").strip().lower() in {"1", "true", "yes"}

app = FastAPI(
    title="My API",
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
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if not _DOCS:
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response
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
    body = ErrorSchema(code=exc.code, message=t(exc.message))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
