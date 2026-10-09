"""The error log: every warning and error the backend and the worker log,
with its traceback, kept in `error_logs` for the Error log page.

`install(source)` adds a logging handler at WARNING to the root logger (and
uvicorn's, which does not propagate): unhandled API and socket errors, failed
Celery tasks and everything the code logs as a warning or an error. Records
go to a queue; a background thread writes them in batches with its own
database connection, so logging never waits for the database and a database
that is down only loses those entries (they still reach the console).
Message and traceback are encrypted (EncryptedText): an error can quote a
document or a chat. Entries older than ERROR_LOG_RETENTION_DAYS are deleted.
"""

import asyncio
import logging
import os
import queue
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from models.error_log import ErrorLog

LEVELS = ("warning", "error", "critical")
SOURCES = ("backend", "worker")
_BATCH = 100
_QUEUE_SIZE = 10_000
# Marks an exception the app already logged, so uvicorn's own report of the
# same exception (it re-raises from the error handler) is not stored twice.
LOGGED = "_corpus_logged"
_FORMATTER = logging.Formatter()


class DatabaseLogHandler(logging.Handler):
    def __init__(self, source: str) -> None:
        super().__init__(logging.WARNING)
        self.source = source
        self._pid: int | None = None
        self._queue: queue.Queue = queue.Queue(_QUEUE_SIZE)
        self._writer: threading.Thread | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if threading.current_thread() is self._writer:
            return  # the writer's own trouble: it would log forever
        exception = record.exc_info[1] if record.exc_info else None
        if record.name.startswith("uvicorn") and getattr(exception, LOGGED, False):
            return
        try:
            entry = {
                "created_at": datetime.fromtimestamp(record.created, UTC),
                "level": record.levelname.lower()[:16],
                "source": self.source,
                "logger": record.name[:128],
                "message": record.getMessage(),
                "traceback": _FORMATTER.formatException(record.exc_info) if record.exc_info else None,
            }
            self._ensure_writer()
            self._queue.put_nowait(entry)
        except queue.Full:
            pass  # a flood: the console still has it
        except Exception:  # noqa: BLE001 - logging must never raise
            self.handleError(record)

    def _ensure_writer(self) -> None:
        """One writer per process: Celery forks its pool after the handler
        is installed, and threads do not survive a fork."""
        if self._pid == os.getpid() and self._writer is not None:
            return
        self._pid = os.getpid()
        self._queue = queue.Queue(_QUEUE_SIZE)
        self._writer = threading.Thread(target=self._write_forever, name="error-log-writer", daemon=True)
        self._writer.start()

    def _write_forever(self) -> None:
        while True:
            batch = [self._queue.get()]
            while len(batch) < _BATCH:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                asyncio.run(_insert(batch))
            except Exception as exc:  # noqa: BLE001 - the database is down; nothing else to tell
                print(f"Error log: could not store {len(batch)} entries: {exc}", file=sys.stderr)
            finally:
                for _ in batch:
                    self._queue.task_done()

    def flush(self, timeout: float = 5.0) -> None:
        """Waits until the queued entries are stored, or `timeout` seconds."""
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.05)


async def _insert(rows: list[dict]) -> None:
    from database import DATABASE_URL

    # Its own engine in this thread's event loop: the app's pool belongs to
    # another loop.
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(ErrorLog), rows)
    finally:
        await engine.dispose()


_installed: DatabaseLogHandler | None = None


def install(source: str) -> DatabaseLogHandler:
    """Stores this process's warnings and errors from now on; once per process."""
    global _installed
    if _installed is None:
        _installed = DatabaseLogHandler(source)
        logging.getLogger().addHandler(_installed)
        # uvicorn's loggers do not propagate to the root one.
        logging.getLogger("uvicorn").addHandler(_installed)
    return _installed


class ErrorLogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_entries(
        self, page: int, per_page: int, level: str | None = None, source: str | None = None
    ) -> tuple[list[ErrorLog], int]:
        """Newest first."""
        conditions = []
        if level is not None:
            conditions.append(ErrorLog.level == level)
        if source is not None:
            conditions.append(ErrorLog.source == source)
        total = await self.session.scalar(select(func.count()).select_from(ErrorLog).where(*conditions))
        entries = await self.session.scalars(
            select(ErrorLog)
            .where(*conditions)
            .order_by(ErrorLog.created_at.desc(), ErrorLog.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(entries), total or 0

    async def purge_older_than(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(delete(ErrorLog).where(ErrorLog.created_at < cutoff))
        await self.session.commit()
        # A DELETE gives a CursorResult; the async API types it as Result.
        return cast(CursorResult, result).rowcount or 0
