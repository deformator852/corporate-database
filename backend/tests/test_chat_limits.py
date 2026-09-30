"""One answer at a time per user; CHAT_QUESTIONS_PER_10_MIN per user."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from conftest import run
from exceptions import AppError


@pytest.fixture
def limit(monkeypatch):
    import services.chat_limit as chat_limit

    def set_limit(value: int) -> None:
        monkeypatch.setattr(chat_limit, "chat_questions_per_10_min", lambda: value)

    set_limit(20)
    return set_limit


def test_second_question_waits_for_the_first_answer(limit, make_user):
    from services.chat_limit import finish_chat_request, start_chat_request

    user_id, _, _ = make_user()
    other_id, _, _ = make_user()
    first = run(start_chat_request(user_id))
    with pytest.raises(AppError) as busy:
        run(start_chat_request(user_id))  # e.g. from another tab
    assert busy.value.code == "busy"
    run(start_chat_request(other_id))  # other users are not affected
    run(finish_chat_request(first))
    run(start_chat_request(user_id))


def test_simultaneous_questions_let_only_one_through(limit, make_user):
    from services.chat_limit import start_chat_request

    user_id, _, _ = make_user()

    async def race() -> list[object]:
        return await asyncio.gather(
            *(start_chat_request(user_id) for _ in range(5)), return_exceptions=True
        )

    results = run(race())
    assert sum(isinstance(r, int) for r in results) == 1


def test_questions_per_10_minutes(limit, make_user):
    from services.chat_limit import finish_chat_request, start_chat_request

    limit(3)
    user_id, _, _ = make_user()
    for _ in range(3):
        run(finish_chat_request(run(start_chat_request(user_id))))
    with pytest.raises(AppError) as limited:
        run(start_chat_request(user_id))
    assert limited.value.code == "rate_limited" and "3 questions" in limited.value.message
    limit(0)  # no limit
    run(start_chat_request(user_id))


def test_crashed_answer_does_not_block_forever(limit, make_user):
    from database import AsyncSessionLocal
    from models import ChatRequest
    from services.chat_limit import start_chat_request

    user_id, _, _ = make_user()
    request_id = run(start_chat_request(user_id))

    async def age() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(ChatRequest)
                .where(ChatRequest.id == request_id)
                .values(started_at=datetime.now(UTC) - timedelta(minutes=20))
            )
            await session.commit()

    run(age())
    run(start_chat_request(user_id))


def test_second_tab_is_refused_until_the_first_answer_stops(client, make_user, limit, monkeypatch):
    import api.v1.chat as chat_api
    from conftest import login

    async def endless_answer(*_args):
        await asyncio.Event().wait()  # an answer still being written

    monkeypatch.setattr(chat_api, "_generate", endless_answer)
    _, email, password = make_user()
    login(client, email, password)
    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
    ask = {"type": "ask", "messages": [{"role": "user", "content": "Salary policy?"}], "conversation_id": None}

    with client.websocket_connect("/api/v1/chat/ws", headers=headers) as first:
        first.send_json(ask)
        with client.websocket_connect("/api/v1/chat/ws", headers=headers) as second:
            second.send_json(ask)
            assert second.receive_json()["code"] == "busy"
            first.send_json({"type": "cancel"})
            assert first.receive_json()["type"] == "cancelled"
            second.send_json(ask)  # the slot is free again: no error comes back
            second.send_json({"type": "cancel"})
            assert second.receive_json()["type"] == "cancelled"
