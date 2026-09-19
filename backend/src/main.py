from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

from api.v1.router import api_router
from exceptions import AppError
from schemas.error_schema import ErrorSchema
from security import security

app = FastAPI(
    title="My API",
    version="1.0.0",
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
