"""A document's life: upload → queue → processing → search → chat → delete,
with realtime events, notifications and encryption at every store."""

import pytest
from conftest import csrf, login, process, run, upload
from sqlalchemy import select, text
from starlette.websockets import WebSocketDisconnect

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

    with (
        client.websocket_connect("/api/v1/documents/ws", headers=_ws(client)) as documents_ws,
        client.websocket_connect("/api/v1/notifications/ws", headers=_ws(client)) as notes_ws,
    ):
        process(document_id)
        statuses = [documents_ws.receive_json()["status"] for _ in range(4)]
        note = notes_ws.receive_json()

    document = _document(document_id)
    assert (document.status, document.progress, document.error_message) == ("completed", 100, None)
    assert statuses[:3] == ["parsing", "chunking", "embedding"]
    points = _points(infra, document_id)
    assert len(points) > 1
    assert all(p["text"].startswith("enc:v2:") and isinstance(p["start"], int) for p in points)
    assert note["user_id"] == owner_id and "Travel policy" in note["message"]
    notifications = client.get("/api/v1/notifications").json()
    assert notifications["unread_count"] == 1 and notifications["items"][0]["type"] == "document.completed"
    raw_text = run(_raw_text(document_id))
    assert raw_text.startswith("enc:v2:") and "budget" not in raw_text


def _notes(client) -> list[tuple[str, str]]:
    return [(n["type"], n["message"]) for n in client.get("/api/v1/notifications").json()["items"]]


def test_a_batch_gets_one_ready_notice_and_each_failure_its_own(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    ids = [
        upload(client, "Policy", POLICY.encode(), "policy.txt").json()["id"],
        upload(client, "Blank", b"   \n  ", "blank.txt").json()["id"],
        upload(client, "Minutes", b"The board met on Friday.", "minutes.txt").json()["id"],
    ]

    process(ids[0])
    assert _notes(client) == []  # the rest of the batch still waits
    process(ids[1])
    process(ids[2])

    assert sorted(_notes(client)) == [
        ("document.process_failed", "The document has no text."),
        ("documents.completed", "2 documents are ready."),
    ]


def test_deleting_the_last_waiting_document_sends_the_ready_notice(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    ready = upload(client, "Policy", POLICY.encode(), "policy.txt").json()["id"]
    waiting = upload(client, "Draft", b"Draft text.", "draft.txt").json()["id"]
    process(ready)
    assert _notes(client) == []

    assert client.delete(f"/api/v1/documents/{waiting}", headers=csrf(client)).status_code == 204

    assert _notes(client) == [("document.completed", '"Policy" is ready.')]


def test_uploads_stop_while_too_many_documents_wait(client, make_user, infra, monkeypatch):
    import services.documents.document as documents

    monkeypatch.setattr(documents, "MAX_WAITING_DOCUMENTS", 2)
    _, email, password = make_user(WRITER)
    login(client, email, password)
    first = upload(client, "One", b"One.", "one.txt").json()["id"]
    upload(client, "Two", b"Two.", "two.txt")

    refused = upload(client, "Three", b"Three.", "three.txt")

    assert refused.status_code == 429 and refused.json()["code"] == "rate_limited"
    process(first)
    assert upload(client, "Three", b"Three.", "three.txt").status_code == 201


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


def test_a_line_many_documents_share_is_found(client, make_user, infra):
    from database import AsyncSessionLocal
    from services.documents.boilerplate import MIN_DOCUMENTS, shared_lines

    _, email, password = make_user(WRITER)
    login(client, email, password)
    notice = "This message is confidential and meant only for the people it was sent to."
    texts = [f"Note {i} about the budget.\n{notice}" for i in range(MIN_DOCUMENTS)]
    ids = [upload(client, f"Note {i}", text.encode(), f"note{i}.txt").json()["id"] for i, text in enumerate(texts)]

    async def shared(document_id: int, text: str) -> frozenset[str]:
        async with AsyncSessionLocal() as session:
            found = await shared_lines(session, document_id, text)
            await session.commit()
            return found

    assert all(run(shared(i, t)) == frozenset() for i, t in zip(ids[:-1], texts[:-1], strict=True))
    assert run(shared(ids[-1], texts[-1])) == frozenset({notice})  # now in enough documents


def test_the_document_list_is_searched_and_filtered(client, make_user, infra):
    _, email, password = make_user([*WRITER, "documents.confidential"])
    login(client, email, password)
    travel = upload(client, "Travel policy", POLICY.encode(), "travel.txt").json()["id"]
    upload(client, "Board minutes", b"Minutes of the board.", "board_2026.txt", "confidential")
    upload(client, "Leave rules", b"Leave is 26 days.", "leave.txt")
    process(travel)

    def names(**params: str) -> list[str]:
        items = client.get("/api/v1/documents", params=params).json()["items"]
        return sorted(item["name"] for item in items)

    assert names(q="POLICY") == ["Travel policy"]
    assert names(q="board_2026") == ["Board minutes"]  # the file name; "_" is literal
    assert names(q="100%") == []
    assert names(status="completed") == ["Travel policy"]
    assert names(status="processing") == ["Board minutes", "Leave rules"]
    assert names(classification="confidential") == ["Board minutes"]
    assert names(q="rules", status="processing") == ["Leave rules"]


def test_the_same_file_is_not_uploaded_twice(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    assert upload(client, "Travel policy", POLICY.encode(), "policy.txt").status_code == 201

    again = upload(client, "Policy copy", POLICY.encode(), "copy.txt")

    assert again.status_code == 409
    assert again.json()["message"] == 'This file is already uploaded as "Travel policy".'


def test_a_hidden_copy_is_not_revealed(client, make_user, infra):
    _, email, password = make_user([*WRITER, "documents.secret"])
    login(client, email, password)
    assert upload(client, "Board minutes", b"Minutes of the board.", "board.txt", "secret").status_code == 201
    client.post("/api/v1/auth/logout", headers=csrf(client))
    _, email, password = make_user(WRITER)
    login(client, email, password)

    # The same file exists, but at a level this user cannot see.
    assert upload(client, "Minutes", b"Minutes of the board.", "minutes.txt").status_code == 201


def test_a_failed_document_is_listed_first_and_processed_again(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    broken = upload(client, "Broken", b'{"a": ', "broken.json").json()["id"]
    process(broken)
    later = upload(client, "Leave rules", b"Leave is 26 days.", "leave.txt").json()["id"]

    assert [item["id"] for item in client.get("/api/v1/documents").json()["items"]][:2] == [broken, later]
    retried = client.post(f"/api/v1/documents/{broken}/retry", headers=csrf(client))

    assert retried.status_code == 200
    assert (retried.json()["status"], retried.json()["error_message"]) == ("queued", None)
    assert infra.queue.ids.count(broken) == 2
    again = client.post(f"/api/v1/documents/{broken}/retry", headers=csrf(client))
    assert (again.status_code, again.json()["message"]) == (409, "Only a failed document can be processed again.")
    assert client.post(f"/api/v1/documents/{later}/retry", headers=csrf(client)).status_code == 409


def test_editing_a_document_changes_it_in_every_store(client, make_user, infra):
    from services.chat.chat import NO_DOCUMENTS_ANSWER

    _, reader_email, reader_password = make_user(["documents.list"])
    _, email, password = make_user([*WRITER, "documents.update", "documents.confidential"])
    login(client, email, password)
    document_id = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]
    url = f"/api/v1/documents/{document_id}"
    assert client.patch(url, headers=csrf(client), json={"name": "Early"}).status_code == 409  # still queued
    process(document_id)
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        _, answer = _collect(chat)

    edited = client.patch(url, headers=csrf(client), json={"name": "Trips", "classification": "confidential"})

    assert edited.status_code == 200 and edited.json()["name"] == "Trips"
    assert (_document(document_id).name, _document(document_id).classification) == ("Trips", "confidential")
    assert {(p["name"], p["classification"]) for p in _points(infra, document_id)} == {("Trips", "confidential")}
    saved = client.get(f"/api/v1/chat/conversations/{answer['conversation_id']}").json()["messages"]
    assert saved[1]["sources"][0]["name"] == "Trips"
    assert client.patch(url, headers=csrf(client), json={"classification": "secret"}).status_code == 403
    assert client.patch(url, headers=csrf(client), json={"name": "  "}).status_code == 400

    async def audited() -> dict:
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            query = text("SELECT details FROM audit_logs WHERE action = 'documents.update' AND target_id = :i")
            return await session.scalar(query, {"i": str(document_id)})

    assert run(audited())["previous_classification"] == "standard"
    client.post("/api/v1/auth/logout", headers=csrf(client))
    login(client, reader_email, reader_password)
    assert client.patch(url, headers=csrf(client), json={"name": "Mine"}).status_code == 403
    assert document_id not in [item["id"] for item in client.get("/api/v1/documents").json()["items"]]
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        _, hidden = _collect(chat)
    assert hidden["content"] == NO_DOCUMENTS_ANSWER


def test_an_edit_is_kept_out_of_postgres_while_search_is_down(client, make_user, infra, monkeypatch):
    from qdrant_client.http.exceptions import ResponseHandlingException

    _, email, password = make_user([*WRITER, "documents.update", "documents.confidential"])
    login(client, email, password)
    document_id = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]
    process(document_id)
    url = f"/api/v1/documents/{document_id}"
    unchanged = client.patch(url, headers=csrf(client), json={"name": "Travel policy"})
    assert unchanged.status_code == 200 and unchanged.json()["name"] == "Travel policy"

    async def down(*args, **kwargs):
        raise ResponseHandlingException(ConnectionError("Qdrant is down"))

    monkeypatch.setattr(infra.qdrant._client, "set_payload", down)
    failed = client.patch(url, headers=csrf(client), json={"name": "Trips", "classification": "confidential"})

    assert failed.status_code == 503
    assert (_document(document_id).name, _document(document_id).classification) == ("Travel policy", "standard")
    assert {(p["name"], p["classification"]) for p in _points(infra, document_id)} == {("Travel policy", "standard")}


def test_search_results_keep_table_values_that_cleanup_rules_drop(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    # A table from a PDF: one cell per line, so values repeat like a header
    # ("Yes") or look like page numbers ("120").
    table = "Team\nApproved\nHeadcount\nSales\nYes\n120\nLegal\nYes\n45\nOps\nYes\n30"
    document_id = upload(client, "Teams", table.encode(), "teams.txt").json()["id"]

    process(document_id)

    from encryption import decrypt_text

    texts = [decrypt_text(p["text"], f"chunk:{document_id}:{p['chunk_index']}") for p in _points(infra, document_id)]
    assert "\n".join(texts) == table


def test_chat_answers_from_documents_the_user_may_read(client, make_user, infra):
    _, email, password = make_user([*WRITER, "documents.secret", "documents.confidential", "documents.restricted"])
    login(client, email, password)
    public = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]
    secret = upload(
        client, "Board minutes", b"The travel budget of the board is secret.", "board.txt", "secret"
    ).json()["id"]
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


def test_an_answer_is_saved_when_the_client_leaves(client, make_user, infra):
    import time

    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])
    infra.llm.delay = 0.05

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        assert _next(chat)["type"] == "delta"  # answering has begun
    # The tab is closed; the answer is still written and saved.

    messages: list[dict] = []
    for _ in range(100):
        items = client.get("/api/v1/chat/conversations").json()["items"]
        if items:
            messages = client.get(f"/api/v1/chat/conversations/{items[0]['id']}").json()["messages"]
            if len(messages) == 2:
                break
        time.sleep(0.05)
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "What is the travel budget?"),
        ("assistant", "The travel budget is 500 EUR."),
    ]


def test_the_chat_is_known_before_the_answer_and_the_answer_by_its_id(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        started = chat.receive_json()
        _, answer = _collect(chat)

    assert started == {"type": "started", "conversation_id": answer["conversation_id"]}
    saved = client.get(f"/api/v1/chat/conversations/{answer['conversation_id']}").json()["messages"]
    assert saved[1]["id"] == answer["message_id"]


def test_a_stopped_answer_keeps_what_was_written(client, make_user, infra):
    import time

    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])
    infra.llm.delay = 0.05

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        conversation_id = chat.receive_json()["conversation_id"]
        first = chat.receive_json()["content"]
        chat.send_json({"type": "cancel"})
        while chat.receive_json()["type"] != "cancelled":
            pass

    messages: list[dict] = []
    for _ in range(40):
        messages = client.get(f"/api/v1/chat/conversations/{conversation_id}").json()["messages"]
        if len(messages) == 2:
            break
        time.sleep(0.05)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"].startswith(first.strip())
    assert messages[1]["content"] != "The travel budget is 500 EUR."  # cut short


def test_rated_answers_reach_those_who_review_them(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        _, answer = _collect(chat)
    conversation, message = answer["conversation_id"], answer["message_id"]
    rating_url = f"/api/v1/chat/conversations/{conversation}/messages/{message}/rating"

    assert client.put(rating_url, headers=csrf(client), json={"rating": "down"}).status_code == 204
    saved = client.get(f"/api/v1/chat/conversations/{conversation}").json()["messages"]
    assert [m["rating"] for m in saved] == [None, "down"]
    question = saved[0]["id"]
    question_url = f"/api/v1/chat/conversations/{conversation}/messages/{question}/rating"
    assert client.put(question_url, headers=csrf(client), json={"rating": "up"}).status_code == 404
    assert client.get("/api/v1/chat/feedback").status_code == 403
    client.post("/api/v1/auth/logout", headers=csrf(client))

    _, reviewer_email, reviewer_password = make_user(["chat.feedback"])
    login(client, reviewer_email, reviewer_password)
    item = client.get("/api/v1/chat/feedback", params={"rating": "down"}).json()["items"][0]
    assert item["conversation_id"] == conversation
    assert (item["question"], item["answer"], item["user"]["email"]) == (
        "What is the travel budget?",
        "The travel budget is 500 EUR.",
        email,
    )
    assert client.put(rating_url, headers=csrf(client), json={"rating": "up"}).status_code == 404  # not theirs
    # Handled: off the page; the chat and the answer stay.
    assert client.delete(f"/api/v1/chat/feedback/{message}", headers=csrf(client)).status_code == 204
    listed = client.get("/api/v1/chat/feedback", params={"rating": "all", "per_page": 100}).json()["items"]
    assert message not in [i["message_id"] for i in listed]
    assert client.delete(f"/api/v1/chat/feedback/{message}", headers=csrf(client)).status_code == 404
    client.post("/api/v1/auth/logout", headers=csrf(client))
    login(client, email, password)
    kept = client.get(f"/api/v1/chat/conversations/{conversation}").json()["messages"]
    assert [m["rating"] for m in kept] == [None, None]
    assert client.put(rating_url, headers=csrf(client), json={"rating": "down"}).status_code == 204
    client.post("/api/v1/auth/logout", headers=csrf(client))
    login(client, reviewer_email, reviewer_password)
    # Every rated answer, each with its own rating; none of the good ones holds it.
    everything = client.get("/api/v1/chat/feedback", params={"rating": "all", "per_page": 100}).json()["items"]
    assert next(i["rating"] for i in everything if i["message_id"] == message) == "down"
    good = client.get("/api/v1/chat/feedback", params={"rating": "up", "per_page": 100}).json()["items"]
    assert message not in [i["message_id"] for i in good]
    client.post("/api/v1/auth/logout", headers=csrf(client))

    login(client, email, password)
    assert client.put(rating_url, headers=csrf(client), json={"rating": None}).status_code == 204
    client.post("/api/v1/auth/logout", headers=csrf(client))
    login(client, reviewer_email, reviewer_password)
    listed = client.get("/api/v1/chat/feedback", params={"rating": "down"}).json()["items"]
    assert message not in [i["message_id"] for i in listed]


def test_chat_answers_only_from_the_chosen_documents(client, make_user, infra, monkeypatch):
    import dataclasses
    import os

    import settings
    from services.chat.chat import NO_DOCUMENTS_ANSWER

    _, email, password = make_user(WRITER)
    login(client, email, password)
    travel = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]
    trips = upload(client, "Trips", b"The travel budget for trips abroad is 900 EUR.", "trips.txt").json()["id"]
    process(travel)
    process(trips)

    def ask(question: str, document_ids: list[int]) -> dict:
        with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
            chat.send_json({**_ask(question), "document_ids": document_ids})
            return _collect(chat)[1]

    infra.llm.answer = "It is 900 EUR.\nSOURCES: Trips"
    answer = ask("What is the travel budget?", [trips])
    assert [source["id"] for source in answer["sources"]] == [trips]
    prompt = str(infra.llm.calls[-1]["messages"])
    assert "900 EUR" in prompt and "500 EUR" not in prompt
    # Scores below any floor, yet the document is the one the user chose.
    key = os.environ["EMBEDDING_MODEL"]
    monkeypatch.setitem(
        settings.EMBEDDING_MODELS, key, dataclasses.replace(settings.EMBEDDING_MODELS[key], min_score=0.99)
    )
    assert ask("Summarize it", [])["content"] == NO_DOCUMENTS_ANSWER
    assert ask("Summarize it", [trips])["content"] != NO_DOCUMENTS_ANSWER
    assert "900 EUR" in str(infra.llm.calls[-1]["messages"])


def test_a_source_shows_the_passage_the_answer_came_from(client, make_user, infra):
    from test_components import _pdf

    _, email, password = make_user([*WRITER, "documents.confidential"])
    login(client, email, password)
    policy = upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"]
    process(policy)

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        _, answer = _collect(chat)

    chunk = answer["sources"][0]["chunk"]
    saved = client.get(f"/api/v1/chat/conversations/{answer['conversation_id']}").json()["messages"][1]
    assert saved["sources"][0]["chunk"] == chunk
    passage = client.get(f"/api/v1/documents/{policy}/chunks/{chunk}").json()
    assert "500 EUR" in passage["text"] and passage["page"] is None  # the budget, not "Section 3."
    assert client.get(f"/api/v1/documents/{policy}/chunks/9999").status_code == 404

    scan = upload(client, "Scan", _pdf("The travel budget is 500 EUR."), "scan.pdf", "confidential").json()["id"]
    process(scan)
    assert client.get(f"/api/v1/documents/{scan}/chunks/0").json()["page"] == 1
    client.post("/api/v1/auth/logout", headers=csrf(client))

    _, reader_email, reader_password = make_user(["documents.list"])
    login(client, reader_email, reader_password)
    assert client.get(f"/api/v1/documents/{scan}/chunks/0").status_code == 404  # above their clearance


def test_a_regenerated_answer_replaces_the_old_one(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])
    question = {"role": "user", "content": "What is the travel budget?"}
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask(question["content"]))
        _, first = _collect(chat)
        regenerate = {**_ask(question["content"]), "conversation_id": first["conversation_id"]}
        infra.llm.answer = "Trips may cost 500 EUR."
        chat.send_json({**regenerate, "replace_message_id": first["message_id"]})
        _, second = _collect(chat)
        chat.send_json({**regenerate, "replace_message_id": first["message_id"]})  # gone already
        stale = _next(chat)

    saved = client.get(f"/api/v1/chat/conversations/{first['conversation_id']}").json()["messages"]
    assert [(m["role"], m["content"]) for m in saved] == [
        ("user", question["content"]),
        ("assistant", "Trips may cost 500 EUR."),
    ]
    assert saved[1]["id"] == second["message_id"] != first["message_id"]
    assert stale == {"type": "error", "code": "conflict", "message": "This answer can no longer be regenerated."}


def test_a_stopped_regeneration_replaces_the_old_answer_with_what_was_written(client, make_user, infra):
    import time

    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        _, first = _collect(chat)
        infra.llm.answer = "Trips abroad may cost up to five hundred euros per person."
        infra.llm.delay = 0.05
        replace = {"conversation_id": first["conversation_id"], "replace_message_id": first["message_id"]}
        chat.send_json({**_ask("What is the travel budget?"), **replace})
        piece = _next(chat)["content"]
        chat.send_json({"type": "cancel"})
        while chat.receive_json()["type"] != "cancelled":
            pass

    url = f"/api/v1/chat/conversations/{first['conversation_id']}"
    for _ in range(40):
        saved = client.get(url).json()["messages"]
        if saved[-1]["id"] != first["message_id"]:
            break
        time.sleep(0.05)
    assert [m["role"] for m in saved] == ["user", "assistant"]
    assert saved[1]["content"].startswith(piece.strip()) and saved[1]["id"] != first["message_id"]


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


def test_chat_says_it_does_not_know_without_documents(client, make_user, infra):
    from services.chat.chat import NO_DOCUMENTS_ANSWER

    _, email, password = make_user([])  # may not read any document
    login(client, email, password)

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("Salary of the CEO?"))
        deltas, answer = _collect(chat)

    assert answer["sources"] == [] and "".join(deltas) == answer["content"] == NO_DOCUMENTS_ANSWER
    assert infra.llm.calls == []  # a model without documents invents answers


def test_follow_up_questions_find_documents_through_the_previous_one(client, make_user, infra, monkeypatch):
    import dataclasses
    import os

    import settings
    from services.chat.chat import NO_DOCUMENTS_ANSWER

    _, email, password = make_user(WRITER)
    login(client, email, password)
    budgets = b"Department budget: engineering 5000000, sales 3500000."
    document_id = upload(client, "Budgets", budgets, "budgets.txt").json()["id"]
    process(document_id)
    key = os.environ["EMBEDDING_MODEL"]
    monkeypatch.setitem(
        settings.EMBEDDING_MODELS, key, dataclasses.replace(settings.EMBEDDING_MODELS[key], min_score=0.1)
    )
    infra.llm.answer = "Sales got 3500000.\nSOURCES: Budgets"
    follow_up = {"role": "user", "content": "What about it?"}  # no word shared with any document
    history = [
        {"role": "user", "content": "Engineering department budget?"},
        {"role": "assistant", "content": "Engineering got 5000000."},
        follow_up,
    ]

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json({"type": "ask", "messages": [follow_up], "conversation_id": None})
        _, alone = _collect(chat)
        chat.send_json({"type": "ask", "messages": history, "conversation_id": None})
        _, answer = _collect(chat)

    assert alone["content"] == NO_DOCUMENTS_ANSWER
    assert [source["id"] for source in answer["sources"]] == [document_id]
    assert "3500000" in infra.llm.calls[-1]["messages"][-1]["content"]


def test_chat_reports_a_missing_model(client, make_user, infra):
    from fakes import model_missing

    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])
    infra.llm.error = model_missing()

    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        reply = _next(chat)

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
        return await session.scalar(text("SELECT text FROM document_texts WHERE document_id = :i"), {"i": document_id})


def _ws(client) -> dict[str, str]:
    return {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}


def _ask(question: str) -> dict:
    return {"type": "ask", "messages": [{"role": "user", "content": question}], "conversation_id": None}


def _next(chat) -> dict:
    """The next message after `started`, which comes first for every question."""
    message = chat.receive_json()
    return chat.receive_json() if message["type"] == "started" else message


def _collect(chat) -> tuple[list[str], dict]:
    deltas: list[str] = []
    while True:
        message = chat.receive_json()
        if message["type"] == "started":
            continue
        if message["type"] == "delta":
            deltas.append(message["content"])
            continue
        assert message["type"] == "answer", message
        return deltas, message


def test_a_deleted_chat_takes_its_ratings_along(client, make_user, infra):
    """Chats are deleted after the retention period or by a purge: their
    questions and answers must not live on in the ratings."""
    from sqlalchemy import text

    from database import AsyncSessionLocal
    from services.chat.history import ChatHistoryService

    _, email, password = make_user(WRITER)
    login(client, email, password)
    process(upload(client, "Travel policy", POLICY.encode(), "policy.txt").json()["id"])
    with client.websocket_connect("/api/v1/chat/ws", headers=_ws(client)) as chat:
        chat.send_json(_ask("What is the travel budget?"))
        _, answer = _collect(chat)
    conversation, message = answer["conversation_id"], answer["message_id"]
    rating_url = f"/api/v1/chat/conversations/{conversation}/messages/{message}/rating"
    assert client.put(rating_url, headers=csrf(client), json={"rating": "down"}).status_code == 204
    client.post("/api/v1/auth/logout", headers=csrf(client))

    async def expire() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE chat_conversations SET updated_at = now() - interval '400 days' WHERE id = :id"),
                {"id": conversation},
            )
            await session.commit()
            await ChatHistoryService(session).purge_older_than(365)

    run(expire())
    _, reviewer_email, reviewer_password = make_user(["chat.feedback"])
    login(client, reviewer_email, reviewer_password)
    listed = client.get("/api/v1/chat/feedback", params={"rating": "all", "per_page": 100}).json()["items"]
    assert message not in [item["message_id"] for item in listed]
