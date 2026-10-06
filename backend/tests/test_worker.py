"""The Celery task around document processing: retries, time limits, lost
jobs, and the worker's start-up checks."""

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from conftest import login, run, upload
from sqlalchemy import select

WRITER = ["documents.list", "documents.create"]


def _status(document_id: int) -> tuple[str, str | None] | None:
    from database import AsyncSessionLocal
    from models import Document

    async def load():
        async with AsyncSessionLocal() as session:
            document = await session.scalar(select(Document).where(Document.id == document_id))
            return None if document is None else (document.status, document.error_message)

    return run(load())


def _queued(client, make_user, content: bytes = b"Holiday rules for 2026.", filename: str = "rules.txt") -> int:
    _, email, password = make_user(WRITER)
    login(client, email, password)
    return upload(client, "Rules", content, filename).json()["id"]


def test_task_processes_a_document(client, make_user, infra):
    from tasks.document import process_document

    document_id = _queued(client, make_user)
    process_document.apply(args=[document_id])
    assert _status(document_id) == ("completed", None)


def test_a_bad_file_fails_without_retries(client, make_user, infra):
    from tasks.document import process_document

    document_id = _queued(client, make_user, b"   ", "blank.txt")
    process_document.apply(args=[document_id])
    assert _status(document_id) == ("failed", "The document has no text.")


def test_a_file_missing_from_storage_is_dropped_after_retries(client, make_user, infra):
    from database import AsyncSessionLocal
    from models import Document
    from tasks.document import process_document

    document_id = _queued(client, make_user)

    async def lose_file() -> None:
        async with AsyncSessionLocal() as session:
            key = await session.scalar(select(Document.object_key).where(Document.id == document_id))
        infra.minio.objects.pop(key)

    run(lose_file())
    process_document.apply(args=[document_id])

    assert _status(document_id) is None  # nothing to process: the row goes
    notes = [e for e in infra.broker.events("notification.events") if "Rules" in e["message"]]
    assert notes and notes[-1]["type"] == "document.process_failed"


def test_a_service_outage_is_retried_then_fails(client, make_user, infra, monkeypatch):
    import tasks.document as task_module
    from exceptions import AppError

    document_id = _queued(client, make_user)
    attempts: list[int] = []

    async def outage(document_id: int) -> None:
        attempts.append(document_id)
        raise AppError("unavailable", "Could not reach Qdrant.", status_code=503)

    monkeypatch.setattr(task_module, "process_document_job", outage)
    task_module.process_document.apply(args=[document_id])

    assert len(attempts) == task_module.PROCESS_MAX_RETRIES + 1
    assert _status(document_id) == ("failed", "Could not reach Qdrant.")


def test_a_hanging_file_fails_at_the_time_limit(client, make_user, infra, monkeypatch):
    import tasks.document as task_module

    document_id = _queued(client, make_user)

    async def hang(document_id: int) -> None:
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(task_module, "process_document_job", hang)
    task_module.process_document.apply(args=[document_id])
    assert _status(document_id) == ("failed", "Processing took too long.")


def test_worker_start_requeues_unfinished_documents(client, make_user, infra, monkeypatch):
    import tasks.document as task_module

    document_id = _queued(client, make_user)
    queued: list[int] = []
    monkeypatch.setattr(task_module.process_document, "delay", queued.append)

    task_module.requeue_unfinished_documents()

    assert document_id in queued


def test_worker_refuses_another_encryption_key(monkeypatch):
    import encryption
    import worker

    worker.check_encryption_key()  # the right key: starts
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "another-key-" + "q" * 32)
    encryption.reset_keys()
    try:
        with pytest.raises(SystemExit, match="not the key"):
            worker.check_encryption_key()
    finally:
        monkeypatch.undo()
        encryption.reset_keys()
