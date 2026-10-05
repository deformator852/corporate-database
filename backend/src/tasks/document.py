import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
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
from worker import celery

logger = logging.getLogger(__name__)

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
    try:
        asyncio.run(process_document_job(document_id))
    except SoftTimeLimitExceeded:
        # Retrying would hang again; fail it right away.
        asyncio.run(fail_document_job(document_id, "Processing took too long."))
    except AppError as exc:
        if exc.code == "not_found":
            # The file is gone: after the retries, drop the document.
            _retry_or(self, exc, lambda: drop_incomplete_document_job(document_id))
        elif exc.status_code >= 500:
            message = exc.message  # `exc` is unbound once this block ends
            _retry_or(self, exc, lambda: fail_document_job(document_id, message))
        else:
            asyncio.run(fail_document_job(document_id, exc.message))
    except Exception as exc:
        _retry_or(
            self, exc, lambda: fail_document_job(document_id, "Could not process the document.")
        )


def _retry_or(task: Task, exc: Exception, give_up: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """Retries with backoff, or runs `give_up` once the retries are used.
    Counted here: past max_retries Celery re-raises `exc` itself instead of
    MaxRetriesExceededError, which would leave the document queued forever."""
    retries = task.request.retries
    if retries >= task.max_retries:
        asyncio.run(give_up())
        return
    raise task.retry(exc=exc, countdown=5 * (2**retries))


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
