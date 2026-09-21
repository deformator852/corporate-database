import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

from api.v1.router import api_router
from exceptions import AppError
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


app = FastAPI(
    title="My API",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(api_router)
security.handle_errors(app)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    body = ErrorSchema(code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
