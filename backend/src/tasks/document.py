import asyncio

from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from worker import celery

PROCESS_MAX_RETRIES = 5
# The worker runs one task at a time, so a file that hangs a parser would stall
# every upload. Soft limit marks the document failed; hard limit kills the task.
PROCESS_SOFT_TIME_LIMIT = 10 * 60
PROCESS_TIME_LIMIT = PROCESS_SOFT_TIME_LIMIT + 60


@celery.task(
    bind=True,
    name="documents.process",
    acks_late=True,
    max_retries=PROCESS_MAX_RETRIES,
    soft_time_limit=PROCESS_SOFT_TIME_LIMIT,
    time_limit=PROCESS_TIME_LIMIT,
)
def process_document(self, document_id: int) -> None:
    from exceptions import AppError
    from services.document_processor import (
        drop_incomplete_document_job,
        fail_document_job,
        process_document_job,
    )

    try:
        asyncio.run(process_document_job(document_id))
    except SoftTimeLimitExceeded:
        # Retrying would hang again; fail it right away.
        asyncio.run(fail_document_job(document_id, "Processing took too long."))
    except AppError as exc:
        countdown = 5 * (2 ** self.request.retries)
        if exc.code == "not_found":
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                asyncio.run(drop_incomplete_document_job(document_id))
            return
        if exc.status_code >= 500:
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                asyncio.run(fail_document_job(document_id, exc.message))
            return
        asyncio.run(fail_document_job(document_id, exc.message))
    except Exception as exc:
        try:
            raise self.retry(
                exc=exc,
                countdown=5 * (2 ** self.request.retries),
            )
        except MaxRetriesExceededError:
            asyncio.run(
                fail_document_job(document_id, "Could not process the document.")
            )
