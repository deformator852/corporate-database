"""Parsing, the LLM client, text cleanup, long-document excerpts, the system
page, socket session checks and app-wide behaviour."""

import io
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from ollama import ResponseError

from conftest import csrf, login, process, run, upload
from exceptions import AppError
from fakes import FakeOllama
from schemas.chat import ChatMessageSchema
from services.documents.parser import DocumentParser
from services.documents.text_cleanup import LlmCleaner
from services.generator import OllamaGenerator, document_budget_chars

# Parsing


def _pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def _docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _xlsx(rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _odt(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr(
            "content.xml",
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
            f"<text:p>{text}</text:p></office:text></office:body></office:document-content>",
        )
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("a.pdf", _pdf("Invoice 42 total 900"), "Invoice 42 total 900"),
        ("a.docx", _docx("Contract clause 3.2"), "Contract clause 3.2"),
        ("a.odt", _odt("Minutes of the board"), "Minutes of the board"),
        ("a.xlsx", _xlsx([["Name", "Salary"], ["Ana", 1200], [None, None]]), "Ana\t1200"),
        ("a.csv", "Name,City\nAna,Madrid\n".encode(), "Ana\tMadrid"),
        ("a.json", '{"city": "París"}'.encode(), '"city": "París"'),
        ("a.xml", b"<root><item>Budget</item><item> </item></root>", "Budget"),
        ("a.md", "# Title\nÉté".encode(), "Été"),
        ("a.TXT", b"plain", "plain"),
    ],
)
def test_every_supported_format_yields_its_text(filename, content, expected):
    assert expected in DocumentParser().parse(content, filename)


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("a.exe", b"MZ", "This file type is not supported."),
        ("a.json", b"{broken", "Could not read the document."),
        ("a.docx", b"not a zip", "Could not read the document."),
        ("a.txt", b"   \n ", "The document has no text."),
    ],
)
def test_unreadable_documents_explain_why(filename, content, message):
    with pytest.raises(AppError) as error:
        DocumentParser().parse(content, filename)
    assert error.value.message == message and error.value.status_code == 400


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_old_word_files_are_converted_on_upload(client, make_user, infra, tmp_path):
    source = tmp_path / "memo.docx"
    source.write_bytes(_docx("Quarterly memo about vacation days"))
    subprocess.run(
        ["soffice", "--headless", f"-env:UserInstallation={(tmp_path / 'lo').as_uri()}",
         "--convert-to", "doc", "--outdir", str(tmp_path), str(source)],
        check=True, capture_output=True, timeout=120,
    )
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)

    response = upload(client, "Memo", (tmp_path / "memo.doc").read_bytes(), "memo.doc")

    assert response.status_code == 201
    assert response.json()["converted"] is True and response.json()["filename"] == "memo.docx"
    process(response.json()["id"])
    items = client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]
    assert next(i for i in items if i["id"] == response.json()["id"])["status"] == "completed"


# LLM client


def _messages(*contents: str) -> list[ChatMessageSchema]:
    roles = ["user", "assistant"]
    return [ChatMessageSchema(role=roles[i % 2], content=c) for i, c in enumerate(contents)]


def test_prompt_carries_documents_recent_history_and_language(monkeypatch):
    monkeypatch.setenv("APP_LANGUAGE", "fr")
    llm = FakeOllama()
    history = ["old question", "x" * 5000, *[f"turn {i}" for i in range(5)], "What is the budget?"]
    documents = [{"filename": "policy.txt", "text": "Budget is 500 EUR."}, {"name": "Empty", "text": " "}]

    answer = run(OllamaGenerator(llm).complete(_messages(*history), documents))

    sent = llm.calls[0]["messages"]
    assert answer == llm.answer
    assert "Always reply in French" in sent[0]["content"]
    assert len(sent) == 1 + 6 and "old question" not in str(sent)  # last 6 messages only
    assert sent[-1]["content"] == "Documents:\n[1] policy.txt\nBudget is 500 EUR.\n\nQuestion:\nWhat is the budget?"
    assert all(len(m["content"]) <= 1501 for m in sent[1:-1])  # older turns are shortened


def test_long_documents_are_cut_to_fit_the_context(monkeypatch):
    monkeypatch.setenv("LLM_NUM_CTX", "4096")
    llm = FakeOllama()
    documents = [{"filename": f"d{i}.txt", "text": "word " * 10_000} for i in range(2)]

    run(OllamaGenerator(llm).complete(_messages("Summarize"), documents))

    prompt = llm.calls[0]["messages"][-1]["content"]
    assert prompt.count("…") == 2 and len(prompt) < 4096 * 3
    assert document_budget_chars(2) == (4096 - 1024 - 1536) * 3 // 2


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ResponseError("missing", 404), "The chat model is not available."),
        (ResponseError("boom", 500), "The chat model failed."),
        (httpx.ConnectError("refused"), "Could not reach the chat model."),
    ],
)
def test_llm_failures_become_clear_errors(error, message):
    llm = FakeOllama()
    llm.error = error
    with pytest.raises(AppError) as raised:
        run(OllamaGenerator(llm).complete(_messages("Hi"), []))
    assert raised.value.message == message and raised.value.status_code == 503


def test_empty_llm_answer_is_an_error():
    llm = FakeOllama()
    llm.answer = "   "
    with pytest.raises(AppError, match="empty answer"):
        run(OllamaGenerator(llm).complete(_messages("Hi"), []))


def test_answer_streams_piece_by_piece():
    llm = FakeOllama()
    pieces: list[str] = []

    async def collect(piece: str) -> None:
        pieces.append(piece)

    run(OllamaGenerator(llm).complete(_messages("Hi"), [], collect))
    assert len(pieces) > 1 and "".join(pieces) == llm.answer


# Text cleanup


@pytest.mark.parametrize(
    ("rewrite", "kept"),
    [
        (lambda p: p.replace("CONFIDENTIAL internal copy ", ""), False),  # a safe cleanup is used
        (lambda p: "Pay the invoice.", True),  # lost the amount: rejected
        (lambda p: f"<<<\n{p.replace('CONFIDENTIAL internal copy ', '')}\n>>>", False),  # echoed markers are stripped
        (lambda p: "", True),
    ],
)
def test_cleanup_keeps_the_original_unless_the_rewrite_is_safe(rewrite, kept):
    llm = FakeOllama()
    llm.cleanup = rewrite
    passage = "CONFIDENTIAL internal copy Pay the invoice of 1 250,50 EUR by 5 May."
    cleaner = LlmCleaner(llm)

    result = run(cleaner.clean(passage))

    assert (result == passage) is kept
    assert "1 250,50" in result and cleaner.rejected == int(kept)


def test_cleanup_survives_an_llm_failure():
    llm = FakeOllama()
    llm.error = httpx.ReadTimeout("slow")
    cleaner = LlmCleaner(llm)
    assert run(cleaner.clean("Keep me 42")) == "Keep me 42" and cleaner.rejected == 1


# Long documents in chat


def test_a_fact_deep_in_a_long_document_reaches_the_llm(client, make_user, infra, monkeypatch):
    monkeypatch.setenv("LLM_NUM_CTX", "4096")
    filler = "\n".join(f"Paragraph {i}: general rules about office supplies and desks." for i in range(400))
    text = filler + "\nThe parking fee for visitors is 7 EUR per hour.\n" + filler
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)
    document_id = upload(client, "Handbook", text.encode(), "handbook.txt").json()["id"]
    process(document_id)

    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
    with client.websocket_connect("/api/v1/chat/ws", headers=headers) as chat:
        chat.send_json({"type": "ask", "messages": [{"role": "user", "content": "parking fee for visitors"}]})
        while chat.receive_json()["type"] != "answer":
            pass

    prompt = infra.llm.calls[-1]["messages"][-1]["content"]
    assert "[Excerpts from a longer document]" in prompt
    assert "parking fee for visitors is 7 EUR" in prompt


# System page


def test_system_page_reports_every_service(client, make_user, infra, monkeypatch):
    import services.system as system

    monkeypatch.setattr(system, "_queue", lambda: {"status": "ok", "detail": "1 worker(s)", "workers": 1, "waiting": 0})
    infra.llm.loaded.add("llama3.1:8b")
    monkeypatch.setenv("LLM_MODEL", "llama3.1:8b")
    _, email, password = make_user(["system.view", "documents.list", "documents.create"])
    login(client, email, password)
    process(upload(client, "Menu", b"Lunch menu.", "menu.txt").json()["id"])

    status = client.get("/api/v1/system/status").json()

    services = {s["name"]: s for s in status["services"]}
    assert set(services) == {"database", "search_index", "storage", "queue", "llm", "embedding", "disk"}
    assert all(s["status"] in {"ok", "warning"} for s in services.values()), services
    assert services["search_index"]["chunks"] >= 1 and services["llm"]["status"] == "ok"
    assert status["documents"]["completed"] >= 1
    assert status["config"]["llm_model"] == "llama3.1:8b" and status["config"]["language"] == "en"


def test_system_page_shows_what_is_broken(client, make_user, infra, monkeypatch):
    import services.system as system

    def queue_down():
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(system, "_queue", queue_down)
    monkeypatch.setenv("LLM_MODEL", "missing:model")
    infra.minio.fail_with = "AccessDenied"
    _, email, password = make_user(["system.view"])
    login(client, email, password)

    services = {s["name"]: s for s in client.get("/api/v1/system/status").json()["services"]}

    assert services["storage"] == {"name": "storage", "status": "down", "detail": "MinIO refused the app user: AccessDenied"}
    assert services["queue"]["status"] == "down" and "broker unreachable" in services["queue"]["detail"]
    assert services["llm"] == {"name": "llm", "status": "down", "detail": "Model missing:model is not downloaded in Ollama."}


def test_queue_check_counts_workers_and_jobs(monkeypatch):
    import worker
    from services.system import _queue

    channel = SimpleNamespace(queue_declare=lambda **k: SimpleNamespace(message_count=3))
    connection = SimpleNamespace(default_channel=channel, __enter__=None)

    class Connection:
        def __enter__(self):
            return connection

        def __exit__(self, *args):
            return False

    fake = SimpleNamespace(
        connection_or_acquire=Connection,
        control=SimpleNamespace(inspect=lambda timeout: SimpleNamespace(ping=lambda: replies)),
    )
    monkeypatch.setattr(worker, "celery", fake)
    replies = {"celery@a": {"ok": "pong"}}
    assert _queue() == {"status": "ok", "detail": "1 worker(s), 3 job(s) waiting", "workers": 1, "waiting": 3}
    replies = {}
    assert _queue()["status"] == "down"


# Sockets end with the session


def test_socket_closes_when_the_token_expires(client, make_user):
    from security import security
    from starlette.websockets import WebSocketDisconnect

    user_id, _, _ = make_user()
    token = security.create_access_token(uid=str(user_id), expiry=timedelta(seconds=1))
    headers = {"origin": "https://testserver", "cookie": f"my_token={token}"}
    with client.websocket_connect("/api/v1/notifications/ws", headers=headers) as socket:
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 4401


def test_socket_closes_when_access_is_taken_away(client, make_user, monkeypatch):
    import api.ws
    from database import AsyncSessionLocal
    from models.rbac.association import role_users
    from sqlalchemy import delete
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(api.ws, "RECHECK_SECONDS", 0.2)
    user_id, email, password = make_user(["documents.list"])
    login(client, email, password)
    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}

    async def revoke() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(role_users).where(role_users.c.user_id == user_id))
            await session.commit()

    with client.websocket_connect("/api/v1/documents/ws", headers=headers) as socket:
        run(revoke())
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 4403


def test_chat_socket_closes_after_sign_out(client, make_user, monkeypatch):
    import api.v1.chat
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(api.v1.chat, "RECHECK_SECONDS", 0.2)
    _, email, password = make_user()
    login(client, email, password)
    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
    with client.websocket_connect("/api/v1/chat/ws", headers=headers) as socket:
        client.post("/api/v1/auth/logout", headers=csrf(client))
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 4401


# App-wide


def test_responses_carry_security_headers_and_no_api_docs(client):
    response = client.get("/health")
    assert response.json() == {"status": "ok"}
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_validation_errors_use_the_common_shape(client, make_user):
    response = client.post("/api/v1/auth/login", json={"email": "nobody", "password": "x"})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid" and response.json()["message"].startswith("email:")


def test_idle_chats_and_old_limit_records_are_purged(make_user):
    from database import AsyncSessionLocal
    from models import ChatConversation, ChatRequest
    from services.chat_history import ChatHistoryService
    from services.chat_limit import purge_chat_requests
    from sqlalchemy import select

    user_id, _, _ = make_user()
    long_ago = datetime.now(UTC) - timedelta(days=100)

    async def scenario() -> tuple[int, int, bool, bool]:
        async with AsyncSessionLocal() as session:
            old = ChatConversation(user_id=user_id, title="old", updated_at=long_ago)
            fresh = ChatConversation(user_id=user_id, title="fresh")
            session.add_all([old, fresh, ChatRequest(user_id=user_id, started_at=long_ago, finished_at=long_ago)])
            await session.commit()
            removed = await ChatHistoryService(session).purge_older_than(90)
            requests = await purge_chat_requests()
            ids = set(await session.scalars(select(ChatConversation.id).where(ChatConversation.user_id == user_id)))
            return removed, requests, old.id in ids, fresh.id in ids

    removed, requests, old_kept, fresh_kept = run(scenario())
    assert removed >= 1 and requests >= 1 and not old_kept and fresh_kept
