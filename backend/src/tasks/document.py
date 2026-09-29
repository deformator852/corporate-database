import asyncio
import logging

from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
from celery.signals import worker_ready

# Imported at module level: broken code stops the worker from starting
# instead of failing inside a task, where the job would be lost.
from exceptions import AppError
from services.documents.processor import (
    drop_incomplete_document_job,
    fail_document_job,
    process_document_job,
    unfinished_document_ids,
)
from settings import text_cleanup_budget_seconds
from worker import celery

logger = logging.getLogger(__name__)

PROCESS_MAX_RETRIES = 5
# The worker runs one task at a time, so a file that hangs a parser would stall
# every upload. Soft limit marks the document failed; hard limit kills the task.
# LLM cleanup has its own budget on top (applies after a worker restart).
PROCESS_SOFT_TIME_LIMIT = 10 * 60 + text_cleanup_budget_seconds()
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


@worker_ready.connect
def requeue_unfinished_documents(**_kwargs: object) -> None:
    """Picks up documents whose job was lost (crash, restart, bug), so none
    stays "queued" forever. A duplicate of a job still in the queue is
    harmless: processing a finished document is a no-op."""
    try:
        ids = asyncio.run(unfinished_document_ids())
    except Exception:
        logger.exception("Could not look up unfinished documents")
        return
    for document_id in ids:
        process_document.delay(document_id)
    if ids:
        logger.warning("Re-queued %s unfinished document(s): %s", len(ids), ids)
