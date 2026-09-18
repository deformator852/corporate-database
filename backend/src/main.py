from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from api.v1.router import api_router

app = FastAPI(
    title="My API",
    version="1.0.0",
)
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
