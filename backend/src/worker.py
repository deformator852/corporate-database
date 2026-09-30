import asyncio

from celery import Celery
from celery.signals import worker_init

from extensions import task_modules
from settings import rabbitmq_url

celery = Celery(
    "corporate",
    broker=rabbitmq_url(),
    backend="rpc://",
    include=["tasks.document", *task_modules()],
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
)


@worker_init.connect
def check_encryption_key(**_kwargs: object) -> None:
    """Refuses to start with another DATA_ENCRYPTION_KEY than the stored
    data's (see services/encryption_key.py). SystemExit, because Celery logs
    and ignores ordinary exceptions from signal handlers."""
    from database import AsyncSessionLocal, engine
    from exceptions import AppError
    from services.encryption_key import verify_encryption_key

    async def check() -> None:
        try:
            async with AsyncSessionLocal() as session:
                await verify_encryption_key(session)
        finally:
            await engine.dispose()

    try:
        asyncio.run(check())
    except AppError as exc:
        raise SystemExit(exc.message) from None
