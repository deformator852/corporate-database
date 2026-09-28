import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

from api.v1.router import api_router
from exceptions import AppError
from extensions import plugins
from schemas.error import ErrorSchema
from security import security
from services.document_events import consume_document_events
from services.document_hub import hub
from services.notification_events import consume_notification_events
from services.notification_hub import dispatch_notification


@asynccontextmanager
async def lifespan(_app: FastAPI):
    document_task = asyncio.create_task(consume_document_events(hub.broadcast))
    notification_task = asyncio.create_task(
        consume_notification_events(dispatch_notification)
    )
    try:
        yield
    finally:
        document_task.cancel()
        notification_task.cancel()
        for task in (document_task, notification_task):
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


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    body = ErrorSchema(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
