"""The error log: warnings and errors of the backend and the worker, stored
encrypted and shown to holders of system.errors."""

import logging
import uuid

from conftest import login, run
from sqlalchemy import text


def _stored() -> None:
    """Waits for the background writer."""
    from services import error_log

    assert error_log._installed is not None  # the app installed it on start
    error_log._installed.flush()


def _raw(marker: str) -> list[tuple[str, str]]:
    from database import AsyncSessionLocal

    async def load() -> list[tuple[str, str]]:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                text("SELECT level, message FROM error_logs ORDER BY id DESC LIMIT 200"),
            )
            return [tuple(row) for row in rows]

    from encryption import decrypt_text

    return [(level, message) for level, message in run(load()) if marker in decrypt_text(message)]


def test_warnings_and_errors_reach_the_page_encrypted(client, make_user):
    marker = uuid.uuid4().hex
    logger = logging.getLogger("services.documents.processor")
    try:
        raise ValueError(f"cannot parse page 3 {marker}")
    except ValueError:
        logger.exception("Processing failed %s", marker)
    logger.warning("Slow embedding %s", marker)
    logger.info("Started %s", marker)  # below WARNING: not kept
    _stored()

    rows = _raw(marker)
    assert sorted(level for level, _ in rows) == ["error", "warning"]
    assert all(message.startswith("enc:") for _, message in rows)  # encrypted at rest

    _, email, password = make_user(["system.errors"])
    login(client, email, password)
    items = client.get("/api/v1/system/errors", params={"per_page": 100}).json()["items"]
    error = next(item for item in items if item["message"] == f"Processing failed {marker}")
    assert error["level"] == "error" and error["source"] == "backend"
    assert error["logger"] == "services.documents.processor"
    assert "ValueError: cannot parse page 3" in error["traceback"]
    only_warnings = client.get("/api/v1/system/errors", params={"level": "warning", "per_page": 100}).json()
    assert {item["level"] for item in only_warnings["items"]} == {"warning"}
    assert client.get("/api/v1/system/errors", params={"level": "info"}).status_code == 400


def test_the_error_log_needs_its_permission(client, make_user):
    _, email, password = make_user(["system.view"])
    login(client, email, password)
    assert client.get("/api/v1/system/errors").status_code == 403


def test_an_unhandled_api_error_is_logged_once_and_answered_in_the_common_shape(infra, make_user, monkeypatch):
    from fastapi.testclient import TestClient

    import api.v1.system
    import main
    from services import error_log

    marker = uuid.uuid4().hex

    async def broken(_session):
        raise RuntimeError(f"bug {marker}")

    monkeypatch.setattr(api.v1.system, "system_status", broken)
    _, email, password = make_user(["system.view", "system.errors"])
    with TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False) as client:
        login(client, email, password)
        response = client.get("/api/v1/system/status", params={"q": "secret search"})

        assert response.status_code == 500
        assert response.json() == {"code": "internal", "message": "Something went wrong. Try again."}
        # The server's own report of the same exception is not stored twice.
        try:
            raise RuntimeError(f"bug {marker}")
        except RuntimeError as exc:
            setattr(exc, error_log.LOGGED, True)
            logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=exc)
        _stored()
        items = client.get("/api/v1/system/errors", params={"per_page": 100}).json()["items"]

    ours = [item for item in items if marker in (item["traceback"] or "")]
    assert [item["message"] for item in ours] == ["Unhandled error on GET /api/v1/system/status"]
    assert "secret search" not in ours[0]["message"]  # no query string


def test_the_workers_task_processes_log_too(client):
    """Celery runs tasks in processes forked after the handler was set up;
    threads do not survive a fork, so each process needs its own writer."""
    import os

    from services.error_log import DatabaseLogHandler

    marker = uuid.uuid4().hex
    handler = DatabaseLogHandler("worker")
    logger = logging.getLogger(f"test.worker.{marker}")
    logger.addHandler(handler)
    logger.propagate = False
    logger.error("Before the fork %s", marker)
    handler.flush()

    pid = os.fork()
    if pid == 0:  # the pool process
        try:
            logger.error("Task failed %s", marker)
            handler.flush()
        finally:
            os._exit(0)
    os.waitpid(pid, 0)

    messages = sorted(message for _, message in _decrypted(marker))
    assert messages == [f"Before the fork {marker}", f"Task failed {marker}"]


def _decrypted(marker: str) -> list[tuple[str, str]]:
    from encryption import decrypt_text

    return [(level, decrypt_text(message)) for level, message in _raw(marker)]


def test_old_entries_are_deleted(client):
    from database import AsyncSessionLocal
    from services.error_log import ErrorLogService

    marker = uuid.uuid4().hex
    logging.getLogger("tasks.document").error("Old failure %s", marker)
    _stored()

    async def age_and_purge() -> int:
        async with AsyncSessionLocal() as session:
            await session.execute(text("UPDATE error_logs SET created_at = now() - interval '40 days'"))
            await session.commit()
            return await ErrorLogService(session).purge_older_than(30)

    assert run(age_and_purge()) >= 1
    assert _raw(marker) == []
