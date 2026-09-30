"""A document's life: upload → queue → processing → search → chat → delete,
with realtime events, notifications and encryption at every store."""

import pytest
from sqlalchemy import select, text
from starlette.websockets import WebSocketDisconnect

from conftest import csrf, login, process, run, upload

POLICY = (
    "Travel policy.\n\n"
    + "\n".join(f"Section {i}. Employees book trains for trips under 600 km." for i in range(40))
    + "\n\nThe travel budget per trip is 500 EUR and needs approval by the manager."
)
WRITER = ["documents.list", "documents.create", "documents.delete"]


def _document(document_id: int):
    from database import AsyncSessionLocal
    from models import Document

    async def load():
        async with AsyncSessionLocal() as session:
            return await session.scalar(select(Document).where(Document.id == document_id))

    return run(load())


def _points(infra, document_id: int) -> list[dict]:
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    async def scroll():
        if not await infra.qdrant.collection_exists("documents"):
            return []
        records, _ = await infra.qdrant.scroll(
            "documents",
            scroll_filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]),
            limit=1000,
            with_payload=True,
        )
        return [r.payload for r in records]

    return run(scroll())


def test_upload_is_stored_encrypted_and_queued(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)

    response = upload(client, "Travel policy", POLICY.encode(), "policy.txt")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued" and body["filename"] == "policy.txt" and body["converted"] is False
    assert infra.queue.ids == [body["id"]]
    stored = infra.minio.objects[_document(body["id"]).object_key]
    assert b"travel budget" not in stored  # encrypted at rest
    listed = client.get("/api/v1/documents").json()
    assert [item["id"] for item in listed["items"]][0] == body["id"]


def test_processing_indexes_chunks_and_tells_the_owner(client, make_user, infra):
    owner_id, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]

    with client.websocket_connect("/api/v1/documents/ws", headers=_ws(client)) as documents_ws, \
            client.websocket_connect("/api/v1/notifications/ws", headers=_ws(client)) as notes_ws:
        process(document_id)
        statuses = [documents_ws.receive_json()["status"] for _ in range(4)]
        note = notes_ws.receive_json()

    document = _document(document_id)
    assert (document.status, document.progress, document.error_message) == ("completed", 100, None)
    assert statuses[0] == "parsing" and "cleaning" in statuses
    points = _points(infra, document_id)
    assert len(points) > 1
    assert all(p["text"].startswith("enc:v2:") and isinstance(p["start"], int) for p in points)
    assert note["user_id"] == owner_id and "Travel policy" in note["message"]
    notifications = client.get("/api/v1/notifications").json()
    assert notifications["unread_count"] == 1 and notifications["items"][0]["type"] == "document.completed"
    raw_text = run(_raw_text(document_id))
    assert raw_text.startswith("enc:v2:") and "budget" not in raw_text


def test_processing_twice_is_harmless(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Policy", POLICY.encode(), "policy.txt").json()["id"]
    process(document_id)
    before = len(_points(infra, document_id))
    process(document_id)  # a re-queued duplicate job
    assert len(_points(infra, document_id)) == before


def test_unreadable_file_fails_with_a_reason(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Broken", b'{"a": ', "broken.json").json()["id"]

    process(document_id)

    document = _document(document_id)
    assert document.status == "failed" and document.error_message == "Could not read the document."
    assert _points(infra, document_id) == []
    notes = client.get("/api/v1/notifications").json()["items"]
    assert notes[0]["type"] == "document.process_failed"


def test_cleanup_rewrite_is_embedded_but_the_original_is_kept(client, make_user, infra, monkeypatch):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    infra.llm.cleanup = lambda passage: passage.replace("Section", "Part")
    document_id = upload(client, "Policy", POLICY.encode(), "policy.txt").json()["id"]

    process(document_id)

    from encryption import decrypt_text

    texts = [decrypt_text(p["text"], f"chunk:{document_id}:{p['chunk_index']}") for p in _points(infra, document_id)]
    assert any("Section" in t for t in texts)  # payload keeps the rules-cleaned original
    assert any(call["stream"] is False for call in infra.llm.calls)


def test_structured_files_skip_the_llm(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    csv = "\n".join(f"{i},Employee {i},{1000 + i}" for i in range(200)).encode()
    document_id = upload(client, "Salaries", csv, "salaries.csv").json()["id"]

    process(document_id)

    assert _document(document_id).status == "completed"
    assert infra.llm.calls == []


def test_chat_answers_from_documents_the_user_may_read(client, make_user, infra):
    _, email, password = make_user([*WRITER, "documents.secret", "documents.confidential", "documents.restricted"])
    login(client, email, password)
    public = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]
    secret = upload(client, "Board minutes", b"The travel budget of the board is secret.", "board.txt", "secret").json()["id"]
    process(public)
    process(secret)
    client.post("/api/v1/auth/logout", headers=csrf(client))
    _, reader_email, reader_password = make_user(["documents.list"])
    login(client, reader_email, reader_password)

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        deltas, answer = _collect(chat)

    assert "".join(deltas).strip() == answer["content"] == "The travel budget is 500 EUR."
    assert [source["id"] for source in answer["sources"]] == [public]
    prompt = infra.llm.calls[-1]["messages"]
    assert "Board minutes" not in str(prompt) and "board.txt" not in str(prompt)
    assert "500 EUR" in prompt[-1]["content"]
    saved = client.get(f"/api/v1/chat/conversations/{answer['conversation_id']}").json()
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][1]["sources"][0]["id"] == public


def test_chat_can_reproduce_a_document_named_in_the_question(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]
    process(document_id)

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("Show the full text of policy.txt"))
        _, answer = _collect(chat)

    assert answer["content"].startswith("policy.txt") and "Section 39." in answer["content"]
    assert not any(call["stream"] for call in infra.llm.calls)  # as stored, not retold by the LLM


def test_chat_without_matching_documents_still_answers(client, make_user, infra):
    _, email, password = make_user([])  # may not read any document
    login(client, email, password)
    infra.llm.answer = "I do not have relevant documents."

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("Salary of the CEO?"))
        _, answer = _collect(chat)

    assert answer["sources"] == [] and answer["content"] == "I do not have relevant documents."


def test_chat_reports_a_missing_model(client, make_user, infra):
    from fakes import model_missing

    _, email, password = make_user([])
    login(client, email, password)
    infra.llm.error = model_missing()

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("Hello?"))
        reply = chat.receive_json()

    assert reply == {"type": "error", "code": "unavailable", "message": "The chat model is not available."}


def test_chat_rejects_malformed_messages(client, make_user, infra):
    _, email, password = make_user([])
    login(client, email, password)
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_text("not json")
        assert chat.receive_json()["code"] == "invalid"
        chat.send_json({"type": "ask", "messages": [{"role": "assistant", "content": "hi"}]})
        assert chat.receive_json()["message"] == "The last message must be from the user."


def test_delete_removes_file_chunks_and_row(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Policy", POLICY.encode(), "policy.txt").json()["id"]
    process(document_id)
    key = _document(document_id).object_key

    assert client.delete(f"/api/v1/documents/{document_id}", headers=csrf(client)).status_code == 204

    assert _document(document_id) is None
    assert key not in infra.minio.objects and _points(infra, document_id) == []
    assert client.delete(f"/api/v1/documents/{document_id}", headers=csrf(client)).status_code == 404


def test_upload_rejects_what_it_cannot_take(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    assert upload(client, "Script", b"#!/bin/sh", "run.sh").json()["message"] == "This file type is not supported."
    assert upload(client, "Empty", b"", "empty.txt").json()["message"] == "The file is empty."
    assert upload(client, "Secret", b"x", "s.txt", "secret").status_code == 403  # above own clearance
    assert infra.queue.ids == []


def test_upload_rolls_back_when_storage_is_down(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    infra.minio.fail_with = "InternalError"

    response = upload(client, "Never stored", b"text", "p.txt")

    assert response.status_code == 503 and response.json()["message"] == "Could not store the document."
    infra.minio.fail_with = None
    items = client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]
    assert all(item["name"] != "Never stored" for item in items)  # no row without a file
    assert infra.queue.ids == []


def test_upload_is_marked_failed_when_the_queue_is_down(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    infra.queue.fail = True

    response = upload(client, "Queued", b"text", "q.txt")

    assert response.status_code == 503
    items = client.get("/api/v1/documents").json()["items"]
    failed = next(item for item in items if item["name"] == "Queued")
    assert failed["status"] == "failed" and failed["error_message"] == "Could not queue the document."


def test_document_list_follows_clearance(client, make_user, infra):
    _, email, password = make_user([*WRITER, "documents.confidential", "documents.restricted"])
    login(client, email, password)
    confidential = upload(client, "Plans", b"plans", "plans.txt", "confidential").json()["id"]
    client.post("/api/v1/auth/logout", headers=csrf(client))
    _, reader_email, reader_password = make_user(["documents.list"])
    login(client, reader_email, reader_password)
    ids = [item["id"] for item in client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]]
    assert confidential not in ids


def test_document_events_follow_clearance(client, make_user, infra):
    _, email, password = make_user([*WRITER, "documents.confidential", "documents.restricted"])
    login(client, email, password)
    hidden = upload(client, "Plans", b"Merger plans for next year.", "plans.txt", "confidential").json()["id"]
    visible = upload(client, "Menu", b"Lunch menu for the week.", "menu.txt").json()["id"]
    client.post("/api/v1/auth/logout", headers=csrf(client))
    _, reader_email, reader_password = make_user(["documents.list"])
    login(client, reader_email, reader_password)

    with client.websocket_connect("/api/v1/documents/ws", headers=_ws(client)) as events:
        process(hidden)
        process(visible)
        first = events.receive_json()

    assert first["id"] == visible  # nothing about the confidential one arrived first


def test_document_events_need_documents_list(client, make_user, infra):
    _, email, password = make_user([])
    login(client, email, password)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/api/v1/documents/ws", headers=_ws(client)):
            pass
    assert closed.value.code == 4403


async def _raw_text(document_id: int) -> str:
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await session.scalar(
            text("SELECT text FROM document_texts WHERE document_id = :i"), {"i": document_id}
        )


def _ws(client) -> dict[str, str]:
    return {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}


def _ask(question: str) -> dict:
    return {"type": "ask", "messages": [{"role": "user", "content": question}], "conversation_id": None}


def _collect(chat) -> tuple[list[str], dict]:
    deltas: list[str] = []
    while True:
        message = chat.receive_json()
        if message["type"] == "delta":
            deltas.append(message["content"])
            continue
        assert message["type"] == "answer", message
        return deltas, message
