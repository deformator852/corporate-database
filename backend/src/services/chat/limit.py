"""Chat limits: one answer at a time per user (across tabs, windows and
backend processes) and CHAT_QUESTIONS_PER_10_MIN questions per user.

Keeps one person from occupying the LLM that everyone shares.
"""

import math
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from database import AsyncSessionLocal
from exceptions import AppError
from i18n import t
from models.chat_request import ChatRequest
from settings import chat_questions_per_10_min

WINDOW = timedelta(minutes=10)
# No answer runs this long: an open row this old was left by a crash.
STALE_AFTER = timedelta(minutes=15)
KEEP_FOR = timedelta(days=1)


async def start_chat_request(user_id: int) -> int:
    """Registers a question; raises AppError when the user already waits for
    an answer or used up the limit. Returns the id for `finish_chat_request`."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ChatRequest)
            .where(
                ChatRequest.user_id == user_id,
                ChatRequest.finished_at.is_(None),
                ChatRequest.started_at < now - STALE_AFTER,
            )
            .values(finished_at=now)
        )
        limit = chat_questions_per_10_min()
        if limit:
            count, oldest = (
                await session.execute(
                    select(func.count(), func.min(ChatRequest.started_at)).where(
                        ChatRequest.user_id == user_id,
                        ChatRequest.started_at > now - WINDOW,
                    )
                )
            ).one()
            if count >= limit:
                minutes = max(1, math.ceil((oldest + WINDOW - now).total_seconds() / 60))
                raise AppError(
                    "rate_limited",
                    t(
                        "You have asked {limit} questions in the last 10 minutes. Try again in {minutes} min.",
                        limit=limit,
                        minutes=minutes,
                    ),
                    status_code=429,
                )
        request = ChatRequest(user_id=user_id, started_at=now)
        session.add(request)
        try:
            await session.commit()
        except IntegrityError as exc:
            raise AppError(
                "busy",
                t("Your previous question is still being answered. Wait for it or stop it."),
                status_code=409,
            ) from exc
        return request.id


async def finish_chat_request(request_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ChatRequest).where(ChatRequest.id == request_id).values(finished_at=datetime.now(UTC))
        )
        await session.commit()


async def close_open_chat_requests() -> None:
    """At backend start: answers of the previous run ended with it. (One
    backend process; with several, STALE_AFTER alone frees crashed rows.)"""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ChatRequest).where(ChatRequest.finished_at.is_(None)).values(finished_at=datetime.now(UTC))
        )
        await session.commit()


async def purge_chat_requests() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(ChatRequest).where(ChatRequest.started_at < datetime.now(UTC) - KEEP_FOR))
        await session.commit()
        # A DELETE gives a CursorResult; the async API types it as Result.
        return cast(CursorResult, result).rowcount or 0
