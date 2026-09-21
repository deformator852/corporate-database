import asyncio

from celery.exceptions import MaxRetriesExceededError

from worker import celery

PROCESS_MAX_RETRIES = 5


@celery.task(
    bind=True,
    name="documents.process",
    acks_late=True,
    max_retries=PROCESS_MAX_RETRIES,
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
