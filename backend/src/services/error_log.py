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
from pathlib import Path
from typing import cast

from sqlalchemy import CursorResult, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from models.error_log import ErrorLog

LEVELS = ("warning", "error", "critical")
# unhandled: an error nothing caught (a bug); app: Corpus logged it itself;
# library: a package Corpus uses failed (its warnings are not kept).
CATEGORIES = ("unhandled", "app", "library")
# Loggers that report errors nothing else caught: the web server's, and
# Celery's for a task that raised.
_UNHANDLED_LOGGERS = ("uvicorn", "celery.app.trace")
# Corpus's own top-level modules and packages (src/): their loggers are the app's.
_SRC = Path(__file__).resolve().parents[1]
_OWN_MODULES = frozenset(
    path.stem for path in _SRC.iterdir() if path.suffix == ".py" or (path / "__init__.py").exists()
)
_BATCH = 100
_QUEUE_SIZE = 10_000
# Entries kept per logger per minute. A damaged PDF can make a parser warn
# for every object in it; past this the minute's rest only reach the console.
_PER_LOGGER_PER_MINUTE = 30
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
        # logger -> (minute, entries kept in it)
        self._recent: dict[str, tuple[int, int]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if threading.current_thread() is self._writer:
            return  # the writer's own trouble: it would log forever
        exception = record.exc_info[1] if record.exc_info else None
        if record.name.startswith("uvicorn") and getattr(exception, LOGGED, False):
            return
        category = category_of(record)
        if category == "library" and record.levelno < logging.ERROR:
            # A package's warnings are its own housekeeping (a deprecation, a
            # damaged PDF object): console only. Its errors are kept.
            return
        if not self._allow(record):
            return
        try:
            entry = {
                "created_at": datetime.fromtimestamp(record.created, UTC),
                "level": record.levelname.lower()[:16],
                "source": self.source,
                "logger": record.name[:128],
                "category": category,
                "message": record.getMessage(),
                "traceback": _FORMATTER.formatException(record.exc_info) if record.exc_info else None,
            }
            self._ensure_writer()
            self._queue.put_nowait(entry)
        except queue.Full:
            pass  # a flood: the console still has it
        except Exception:  # noqa: BLE001 - logging must never raise
            self.handleError(record)

    def _allow(self, record: logging.LogRecord) -> bool:
        minute = int(record.created // 60)
        start, kept = self._recent.get(record.name, (minute, 0))
        if start != minute:
            kept = 0
        if kept >= _PER_LOGGER_PER_MINUTE:
            return False
        if len(self._recent) > 1000:
            self._recent.clear()  # many loggers: forget old minutes
        self._recent[record.name] = (minute, kept + 1)
        return True

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


def category_of(record: logging.LogRecord) -> str:
    """`extra={"category": ...}` when the code says; else by the logger."""
    stated = getattr(record, "category", None)
    if stated in CATEGORIES:
        return stated
    if record.name.startswith(_UNHANDLED_LOGGERS):
        return "unhandled"
    return "app" if record.name.split(".")[0] in _OWN_MODULES else "library"


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
        self,
        page: int,
        per_page: int,
        level: str | None = None,
        category: str | None = None,
    ) -> tuple[list[ErrorLog], int]:
        """Newest first."""
        conditions = []
        if category is not None:
            conditions.append(ErrorLog.category == category)
        if level is not None:
            conditions.append(ErrorLog.level == level)
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
