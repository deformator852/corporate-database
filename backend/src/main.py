import asyncio
import logging
import os
from contextlib import asynccontextmanager

from authx.exceptions import JWTDecodeError
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

from api.v1.router import api_router
from exceptions import AppError
from extensions import plugins
from schemas.error import ErrorSchema
from security import security
from services.documents.events import consume_document_events
from services.documents.hub import hub
from services.embedding import get_embedding_model
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    warm_up_task = asyncio.create_task(warm_up())
    document_task = asyncio.create_task(consume_document_events(hub.broadcast))
    notification_task = asyncio.create_task(
        consume_notification_events(dispatch_notification)
    )
    try:
        yield
    finally:
        warm_up_task.cancel()
        document_task.cancel()
        notification_task.cancel()
        for task in (warm_up_task, document_task, notification_task):
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
security.handle_errors(app)
for plugin in plugins():
    if hasattr(plugin, "setup"):
        plugin.setup(app)


# authx answers an undecodable token (bad signature, e.g. after JWT_SECRET_KEY
# changed) with 422; clients sign in again only on 401.
@app.exception_handler(JWTDecodeError)
async def invalid_token_handler(_request: Request, _exc: JWTDecodeError) -> JSONResponse:
    body = ErrorSchema(code="unauthorized", message="Not authenticated")
    return JSONResponse(status_code=401, content=body.model_dump())


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    body = ErrorSchema(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
