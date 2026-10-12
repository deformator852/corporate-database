"""Chats and notifications belong to their owner only; server messages are translated."""

from conftest import csrf, login, run


def _conversation(user_id: int) -> int:
    from database import AsyncSessionLocal
    from services.chat.history import ChatHistoryService

    async def create() -> int:
        async with AsyncSessionLocal() as session:
            history = ChatHistoryService(session)
            conversation = await history.open_or_start(user_id, None, "Salary of the CFO?")
            await history.add_message(conversation, "user", "Salary of the CFO?")
            await session.commit()
            return conversation.id

    return run(create())


def test_chats_are_private(client, make_user):
    owner_id, owner_email, owner_password = make_user()
    _, email, password = make_user()
    conversation = _conversation(owner_id)
    login(client, email, password)
    assert client.get(f"/api/v1/chat/conversations/{conversation}").status_code == 404
    assert client.get("/api/v1/chat/conversations").json()["total"] == 0
    login(client, owner_email, owner_password)
    chat = client.get(f"/api/v1/chat/conversations/{conversation}").json()
    assert chat["title"] == "Salary of the CFO?" and len(chat["messages"]) == 1
    # Only those who may clear chat history delete chats, not their owners.
    assert client.delete(f"/api/v1/chat/conversations/{conversation}", headers=csrf(client)).status_code == 405


def test_users_search_their_own_chats(client, make_user):
    from database import AsyncSessionLocal
    from services.chat.history import ChatHistoryService

    owner_id, email, password = make_user()
    other_id, _, _ = make_user()
    salary = _conversation(owner_id)  # "Salary of the CFO?"
    others = _conversation(other_id)

    async def chat_with_answer() -> int:
        async with AsyncSessionLocal() as session:
            history = ChatHistoryService(session)
            conversation = await history.open_or_start(owner_id, None, "Travel rules?")
            await history.add_message(conversation, "user", "Travel rules?")
            await history.add_message(conversation, "assistant", "Trains under 600 km, per the Travel policy.")
            await session.commit()
            return conversation.id

    travel = run(chat_with_answer())
    login(client, email, password)

    def found(q: str) -> list[int]:
        return [item["id"] for item in client.get("/api/v1/chat/conversations", params={"q": q}).json()["items"]]

    assert found("cfo") == [salary]  # the title, any case
    assert found("TRAINS under") == [travel]  # an answer's text
    assert others not in found("salary")
    assert found("100%") == []
    assert set(found("")) >= {salary, travel}


def test_chat_history_is_read_only_for_users_with_no_less_access(client, make_user):
    owner_id, _, _ = make_user(["documents.list", "documents.secret"])
    conversation = _conversation(owner_id)
    _, email, password = make_user(["chat.history"])
    login(client, email, password)

    # The owner may read secret documents the reviewer may not: hidden.
    listed = client.get("/api/v1/chat/review/conversations", params={"per_page": 100}).json()["items"]
    assert conversation not in [item["id"] for item in listed]
    assert client.get(f"/api/v1/chat/review/conversations/{conversation}").status_code == 404

    _, email, password = make_user(["chat.history", "documents.list", "documents.secret"])
    login(client, email, password)
    listed = client.get("/api/v1/chat/review/conversations", params={"user_id": owner_id}).json()["items"]
    assert [(item["id"], item["message_count"], item["user"]["id"]) for item in listed] == [(conversation, 1, owner_id)]
    chat = client.get(f"/api/v1/chat/review/conversations/{conversation}").json()
    assert chat["messages"][0]["content"] == "Salary of the CFO?" and chat["user"]["id"] == owner_id
    assert {"conversation_id": conversation} in _audited("chat.view")  # never the question
    assert client.post("/api/v1/chat/review/purge", headers=csrf(client), json={}).status_code == 403


def test_chat_history_is_cleared_for_a_period(client, make_user):
    from datetime import UTC, datetime, timedelta

    owner_id, _, _ = make_user(["documents.list"])
    other_id, _, _ = make_user(["documents.list"])
    now = datetime.now(UTC)
    recent, old, others = _conversation(owner_id), _conversation(owner_id), _conversation(other_id)
    _set_updated(old, now - timedelta(days=40))
    _, email, password = make_user(["chat.history", "chat.purge", "documents.list"])
    login(client, email, password)

    def purge(**body) -> int:
        response = client.post("/api/v1/chat/review/purge", headers=csrf(client), json=body)
        assert response.status_code == 200, response.json()
        return response.json()["deleted"]

    def remaining() -> set[int]:
        items = client.get("/api/v1/chat/review/conversations", params={"per_page": 100}).json()["items"]
        return {item["id"] for item in items} & {recent, old, others}

    week_ago = (now - timedelta(days=7)).isoformat()
    assert purge(user_id=owner_id, since=week_ago) == 1  # the owner's recent chat only
    assert remaining() == {old, others}
    month_ago = (now - timedelta(days=30)).isoformat()
    assert purge(since=(now - timedelta(days=60)).isoformat(), until=month_ago) == 1
    assert remaining() == {others}
    reversed_period = {"since": week_ago, "until": month_ago}
    assert client.post("/api/v1/chat/review/purge", headers=csrf(client), json=reversed_period).status_code == 400
    assert _audited("chat.purge")[0]["deleted"] == 1


def test_chat_history_of_someone_with_more_access_cannot_be_cleared(client, make_user):
    admin_id, _, _ = make_user(["documents.list", "documents.secret"])
    conversation = _conversation(admin_id)
    _, email, password = make_user(["chat.purge", "documents.list"])
    login(client, email, password)

    assert client.post("/api/v1/chat/review/purge", headers=csrf(client), json={"user_id": admin_id}).status_code == 403
    assert client.post("/api/v1/chat/review/purge", headers=csrf(client), json={"user_id": 999999}).status_code == 404
    client.post("/api/v1/chat/review/purge", headers=csrf(client), json={})  # everything it may reach
    assert run(_exists(conversation))


def test_one_chat_is_deleted_whole_by_those_who_may(client, make_user):
    owner_id, _, _ = make_user(["documents.list"])
    conversation = _conversation(owner_id)
    stronger_id, _, _ = make_user(["documents.list", "documents.secret"])
    guarded = _conversation(stronger_id)

    _, viewer_email, viewer_password = make_user(["chat.history", "documents.list"])
    login(client, viewer_email, viewer_password)
    url = f"/api/v1/chat/review/conversations/{conversation}"
    assert client.delete(url, headers=csrf(client)).status_code == 403  # reading is not deleting
    client.post("/api/v1/auth/logout", headers=csrf(client))

    _, email, password = make_user(["chat.purge", "documents.list"])
    login(client, email, password)
    assert client.delete(url, headers=csrf(client)).status_code == 204
    assert not run(_exists(conversation))
    assert client.delete(url, headers=csrf(client)).status_code == 404
    # Someone with more access than the actor: as if it did not exist.
    guarded_url = f"/api/v1/chat/review/conversations/{guarded}"
    assert client.delete(guarded_url, headers=csrf(client)).status_code == 404
    assert run(_exists(guarded))
    assert {"conversation_id": conversation, "messages": 1} in _audited("chat.delete")


async def _exists(conversation_id: int) -> bool:
    from database import AsyncSessionLocal
    from models.chat import ChatConversation

    async with AsyncSessionLocal() as session:
        return await session.get(ChatConversation, conversation_id) is not None


def _set_updated(conversation_id: int, when) -> None:
    from sqlalchemy import text

    from database import AsyncSessionLocal

    async def update() -> None:
        async with AsyncSessionLocal() as session:
            query = text("UPDATE chat_conversations SET updated_at = :when WHERE id = :id")
            await session.execute(query, {"when": when, "id": conversation_id})
            await session.commit()

    run(update())


def _audited(action: str) -> list[dict]:
    from sqlalchemy import text

    from database import AsyncSessionLocal

    async def load() -> list[dict]:
        async with AsyncSessionLocal() as session:
            query = text("SELECT details FROM audit_logs WHERE action = :a ORDER BY id DESC")
            return list(await session.scalars(query, {"a": action}))

    return run(load())


def test_notifications_can_only_be_dismissed_by_their_owner(client, make_user):
    from database import AsyncSessionLocal
    from models import Notification

    owner_id, owner_email, owner_password = make_user()
    _, email, password = make_user()

    async def create() -> int:
        async with AsyncSessionLocal() as session:
            note = Notification(user_id=owner_id, type="document.completed", message="ready", read=False)
            session.add(note)
            await session.commit()
            return note.id

    note_id = run(create())
    login(client, email, password)
    assert client.delete(f"/api/v1/notifications/{note_id}", headers=csrf(client)).status_code == 404
    login(client, owner_email, owner_password)
    assert client.delete(f"/api/v1/notifications/{note_id}", headers=csrf(client)).status_code == 204


def test_messages_follow_the_system_language(monkeypatch):
    from i18n import t

    monkeypatch.setenv("APP_LANGUAGE", "fr")
    assert t("The file is empty.") == "Le fichier est vide."
    assert t('"{name}" is ready.', name="Budget") == "« Budget » est prêt."
    assert t("Unknown message") == "Unknown message"
