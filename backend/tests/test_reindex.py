"""Changing EMBEDDING_MODEL by hand: the backend and the worker keep running,
chat search is off and documents wait until an admin rebuilds the search
index from the System page."""

import os

from conftest import csrf, login, process, run, upload

_PERMISSIONS = ["documents.list", "documents.create", "system.view", "system.rechunk", "audit.list"]


def _ws(client) -> dict[str, str]:
    return {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}


def _ask(client) -> dict:
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(
            {
                "type": "ask",
                "messages": [{"role": "user", "content": "When are salaries paid?"}],
                "conversation_id": None,
            }
        )
        message = chat.receive_json()
        return chat.receive_json() if message["type"] == "started" else message


def _status(client, document_id: int) -> str:
    items = client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]
    return next(item["status"] for item in items if item["id"] == document_id)


def _restore_index_model(model: str) -> None:
    from database import AsyncSessionLocal
    from services.search.index_model import save_index_model

    async def restore() -> None:
        async with AsyncSessionLocal() as session:
            await save_index_model(session, model)

    run(restore())


def test_a_changed_embedding_model_is_rebuilt_from_the_system_page(client, make_user, infra, monkeypatch):
    old_model = os.environ["EMBEDDING_MODEL"]
    _, email, password = make_user(_PERMISSIONS)
    login(client, email, password)
    indexed = upload(client, "Payroll", b"Salaries are paid on the 25th.", "payroll.txt").json()["id"]
    process(indexed)
    assert client.get("/api/v1/system/status").json()["outdated_index_model"] is None
    # Nothing to rebuild while the index matches.
    assert client.post("/api/v1/system/reindex", headers=csrf(client)).status_code == 409

    monkeypatch.setenv("EMBEDDING_MODEL", "bge-small-en")  # .env edited by hand
    try:
        assert client.get("/api/v1/system/status").json()["outdated_index_model"] == old_model
        # Search would compare unrelated vectors: off, and the chat says why.
        reply = _ask(client)
        assert (reply["type"], reply["code"]) == ("error", "unavailable")
        assert "System page" in reply["message"]
        # The worker leaves new uploads queued: rebuilding embeds them anyway.
        waiting = upload(client, "Leave", b"Leave requests go to HR.", "leave.txt").json()["id"]
        process(waiting)
        assert _status(client, waiting) == "queued"

        infra.queue.ids.clear()
        started = client.post("/api/v1/system/reindex", headers=csrf(client))
        assert started.status_code == 200 and started.json()["documents"] >= 1
        assert _status(client, indexed) == "queued"
        assert {indexed, waiting} <= set(infra.queue.ids)
        assert client.get("/api/v1/system/status").json()["outdated_index_model"] is None
        assert client.post("/api/v1/system/reindex", headers=csrf(client)).status_code == 409

        for document_id in (indexed, waiting):
            process(document_id)
            assert _status(client, document_id) == "completed"
        assert _ask(client)["type"] in ("delta", "answer")  # search is back

        entries = client.get("/api/v1/audit", params={"action": "system.reindex", "q": email}).json()["items"]
        assert [entry["details"] for entry in entries] == [
            {"from": old_model, "to": "bge-small-en", "documents": started.json()["documents"]}
        ]
    finally:
        _restore_index_model(old_model)


def test_rebuilding_the_index_needs_its_permission(client, make_user, monkeypatch):
    _, email, password = make_user(["system.view"])
    login(client, email, password)
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-small-en")
    assert client.post("/api/v1/system/reindex", headers=csrf(client)).status_code == 403
