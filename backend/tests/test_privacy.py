"""Chats and notifications belong to their owner only; server messages are translated."""

from conftest import csrf, login, run


def _conversation(user_id: int) -> int:
    from database import AsyncSessionLocal
    from services.chat_history import ChatHistoryService

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
    assert client.delete(f"/api/v1/chat/conversations/{conversation}", headers=csrf(client)).status_code == 404
    assert client.get("/api/v1/chat/conversations").json()["total"] == 0
    login(client, owner_email, owner_password)
    chat = client.get(f"/api/v1/chat/conversations/{conversation}").json()
    assert chat["title"] == "Salary of the CFO?" and len(chat["messages"]) == 1


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
