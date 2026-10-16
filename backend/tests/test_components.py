"""Parsing, the LLM client, long-document excerpts, the system
page, socket session checks and app-wide behaviour."""

import io
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from conftest import csrf, login, process, run, upload
from fakes import FakeOllama
from ollama import ResponseError

from exceptions import AppError
from schemas.chat import ChatMessageSchema
from services.chat.context_document import ContextDocument
from services.chat.generator import OllamaGenerator, document_budget_chars
from services.documents.parser import DocumentParser

# Parsing


def _pdf(text: str, extra: str = "") -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET {extra}".encode()
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


def _docx_table(rows: list[list[str]]) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph("Budgets")
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    for cells, values in zip(table.rows, rows, strict=True):
        for cell, value in zip(cells.cells, values, strict=True):
            cell.text = value
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


def _ruled_table(rows: list[list[str]], top: int = 680) -> str:
    """PDF drawing commands for a table with grid lines, as office programs
    export one: 150 x 20 points per cell."""
    commands = []
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            commands.append(f"BT /F1 10 Tf {78 + 150 * c} {top - 20 * r - 14} Td ({value}) Tj ET")
    bottom, right = top - 20 * len(rows), 72 + 150 * len(rows[0])
    commands += [f"72 {top - 20 * r} m {right} {top - 20 * r} l S" for r in range(len(rows) + 1)]
    commands += [f"{72 + 150 * c} {top} m {72 + 150 * c} {bottom} l S" for c in range(len(rows[0]) + 1)]
    return " ".join(commands)


def test_a_pdf_table_keeps_each_row_on_one_line():
    table = [["Department", "Budget"], ["Engineering", "5000000"], ["Sales", "3500000"]]
    text = DocumentParser().parse(_pdf("Budgets 2025", _ruled_table(table)), "budgets.pdf")
    assert text.split("\n") == ["Budgets 2025", "Department\tBudget", "Engineering\t5000000", "Sales\t3500000"]


def test_word_and_odt_headings_become_markdown():
    from docx import Document

    document = Document()
    document.add_heading("Hotels", 1)
    document.add_paragraph("Up to 180 EUR per night.")
    document.add_heading("Taxis", 2)
    buffer = io.BytesIO()
    document.save(buffer)
    assert DocumentParser().parse(buffer.getvalue(), "a.docx") == "# Hotels\nUp to 180 EUR per night.\n## Taxis"
    odt = _odt(
        '</text:p><text:h text:outline-level="2">Taxis</text:h>'
        "<text:p>Night<text:s/>only, <text:span>after</text:span> 23:00."
    )
    assert DocumentParser().parse(odt, "a.odt") == "## Taxis\nNight only, after 23:00."


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
        (
            "a.docx",
            _docx_table([["Department", "Budget"], ["Sales", "1.2M"]]),
            "Budgets\nDepartment\tBudget\nSales\t1.2M",
        ),
        ("a.odt", _odt("Minutes of the board"), "Minutes of the board"),
        ("a.xlsx", _xlsx([["Name", "Salary"], ["Ana", 1200], [None, None]]), "Ana\t1200"),
        ("a.csv", b"Name,City\nAna,Madrid\n", "Ana\tMadrid"),
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
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation={(tmp_path / 'lo').as_uri()}",
            "--convert-to",
            "doc",
            "--outdir",
            str(tmp_path),
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)

    response = upload(client, "Memo", (tmp_path / "memo.doc").read_bytes(), "memo.doc")

    assert response.status_code == 201
    assert response.json()["converted"] is True and response.json()["filename"] == "memo.docx"
    process(response.json()["id"])
    items = client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]
    assert next(i for i in items if i["id"] == response.json()["id"])["status"] == "completed"


def test_docx_named_doc_is_taken_as_docx(client, make_user, infra):
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)

    response = upload(client, "Memo", _docx("Quarterly memo about vacation days"), "memo.doc")

    assert response.status_code == 201
    assert response.json()["converted"] is True and response.json()["filename"] == "memo.docx"
    process(response.json()["id"])
    items = client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]
    assert next(i for i in items if i["id"] == response.json()["id"])["status"] == "completed"


def test_other_zip_named_doc_is_rejected(client, make_user, infra):
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<x/>")

    response = upload(client, "Sheet", buffer.getvalue(), "sheet.doc")

    assert response.status_code == 400
    assert response.json()["message"] == "The file content does not match its type."


# LLM client


def _doc(document_id: int, text: str, *, name: str = "", filename: str = "") -> ContextDocument:
    return ContextDocument(document_id, name, filename, "standard", text)


def _messages(*contents: str) -> list[ChatMessageSchema]:
    roles = ["user", "assistant"]
    return [ChatMessageSchema(role=roles[i % 2], content=c) for i, c in enumerate(contents)]


def test_prompt_carries_documents_recent_history_and_language(monkeypatch):
    monkeypatch.setenv("APP_LANGUAGE", "fr")
    llm = FakeOllama()
    history = ["old question", "old answer", *[f"turn {i}" for i in range(9)], "What is the budget?"]
    documents = [_doc(1, "Budget is 500 EUR.", filename="policy.txt"), _doc(2, " ", name="Empty")]

    answer, _ = run(OllamaGenerator(llm).complete(_messages(*history), documents))

    sent = llm.calls[0]["messages"]
    assert answer == llm.answer
    assert "Always reply in French" in sent[0]["content"]
    assert [m["content"] for m in sent[1:-1]] == history[:-1]  # the whole chat fits
    assert sent[-1]["content"].startswith(
        "Documents:\nDocument: policy.txt\nBudget is 500 EUR.\n\nQuestion:\nWhat is the budget?"
    )
    assert "SOURCES:" in sent[-1]["content"]


def test_history_keeps_the_newest_messages_within_a_quarter_of_the_context(monkeypatch):
    monkeypatch.setenv("LLM_NUM_CTX", "4096")  # history: 1024 tokens = 3072 chars
    llm = FakeOllama()
    history = ["first question", "a" * 2000, "second question", "b" * 2000, "Third question?"]

    run(OllamaGenerator(llm).complete(_messages(*history), []))

    sent = [m["content"] for m in llm.calls[0]["messages"][1:]]
    assert sent[1:] == ["second question", "b" * 2000, "Third question?"]
    assert sent[0].endswith("…") and set(sent[0][:-1]) == {"a"}  # the oldest kept is cut
    assert "first question" not in sent
    assert sum(len(content) for content in sent) <= 3072 + 1


def test_long_documents_are_cut_to_fit_the_context(monkeypatch):
    monkeypatch.setenv("LLM_NUM_CTX", "4096")
    llm = FakeOllama()
    documents = [_doc(i, "word " * 10_000, filename=f"d{i}.txt") for i in range(2)]

    run(OllamaGenerator(llm).complete(_messages("Summarize"), documents))

    prompt = llm.calls[0]["messages"][-1]["content"]
    assert prompt.count("…") == 2 and len(prompt) < 4096 * 3
    assert document_budget_chars(2) == (4096 - 1024 - 1024 - 512) * 3 // 2


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

    monkeypatch.setattr(system, "_queue", lambda: {"status": "ok", "detail": "1 worker", "workers": 1, "waiting": 0})
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
    assert status["config"]["llm_model"] == "llama3.1:8b" and status["config"]["languages"] == ["en"]


def test_system_page_shows_what_is_broken(client, make_user, infra, monkeypatch):
    import services.system as system

    def queue_down():
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(system, "_queue", queue_down)
    monkeypatch.setenv("LLM_MODEL", "missing:model")
    infra.files.fail()
    _, email, password = make_user(["system.view"])
    login(client, email, password)

    services = {s["name"]: s for s in client.get("/api/v1/system/status").json()["services"]}

    assert services["storage"]["status"] == "down"
    assert services["storage"]["detail"].startswith("Cannot create the folder")
    assert services["queue"]["status"] == "down" and "broker unreachable" in services["queue"]["detail"]
    assert services["llm"] == {
        "name": "llm",
        "status": "down",
        "detail": "Model missing:model is not downloaded in Ollama.",
    }


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
    assert _queue() == {"status": "ok", "detail": "1 worker, 3 jobs waiting", "workers": 1, "waiting": 3}
    replies = {}
    assert _queue()["status"] == "down"


# Sockets end with the session


def test_socket_closes_when_the_token_expires(client, make_user):
    from starlette.websockets import WebSocketDisconnect

    from security import security

    user_id, _, _ = make_user()
    token = security.create_access_token(uid=str(user_id), expiry=timedelta(seconds=1))
    headers = {"origin": "https://testserver", "cookie": f"my_token={token}"}
    with client.websocket_connect("/api/v1/notifications/ws", headers=headers) as socket:
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 4401


def test_socket_closes_when_access_is_taken_away(client, make_user, monkeypatch):
    from sqlalchemy import delete
    from starlette.websockets import WebSocketDisconnect

    import api.ws
    from database import AsyncSessionLocal
    from models.rbac.association import role_users

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
    from starlette.websockets import WebSocketDisconnect

    import api.v1.chat

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
    from sqlalchemy import select

    from database import AsyncSessionLocal
    from models import ChatConversation, ChatRequest
    from services.chat.history import ChatHistoryService
    from services.chat.limit import purge_chat_requests

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


def test_a_failed_commit_is_reported_not_answered_with_success(client, make_user, monkeypatch):
    # The session commits before the response is sent: the client never sees
    # 200 for a change that was not saved, and a refetch right after the
    # response already reads the new state.
    from sqlalchemy.ext.asyncio import AsyncSession

    _, email, password = make_user(admin=True)
    target_id, _, _ = make_user()
    login(client, email, password)

    async def failing_commit(self):
        raise RuntimeError("database went away")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    client_no_raise = client.__class__(client.app, base_url="https://testserver", raise_server_exceptions=False)
    client_no_raise.cookies = client.cookies
    response = client_no_raise.post(f"/api/v1/users/{target_id}/disable", headers=csrf(client))
    assert response.status_code == 500


# Sources the model names


DOCS = [
    _doc(1, "Meals: 47 EUR a day.", name="Travel policy", filename="policy.txt"),
    _doc(2, "Lunch costs 6.50 EUR.", name="Canteen", filename="canteen.txt"),
]


@pytest.mark.parametrize(
    ("answer", "text", "used"),
    [
        ("Meals are 47 EUR a day.\nSOURCES: policy.txt", "Meals are 47 EUR a day.", [1]),
        # Named, but the answer holds nothing from the canteen document: not a source.
        ("Meals are 47 EUR a day.\n**Sources:** Travel policy; Canteen", "Meals are 47 EUR a day.", [1]),
        ("I do not have relevant documents.\nSOURCES: none", "I do not have relevant documents.", []),
        ("Meals are 47 EUR a day.", "Meals are 47 EUR a day.", [1]),  # no line: every supported document
        ("I have no relevant documents.\nSOURCES: policy.txt", "I have no relevant documents.", []),
    ],
)
def test_the_sources_line_is_cut_and_names_the_used_documents(answer, text, used):
    llm = FakeOllama()
    llm.answer = answer
    streamed: list[str] = []

    async def collect(piece: str) -> None:
        streamed.append(piece)

    content, documents = run(OllamaGenerator(llm).complete(_messages("Meal allowance?"), DOCS, collect))

    assert content == text
    assert "".join(streamed).strip() == text  # never shown, even while streaming
    assert [d.document_id for d in documents] == used


def test_a_sources_line_split_across_pieces_is_still_hidden():
    from services.chat.answer_sources import HideSourcesLine

    shown: list[str] = []

    async def collect(piece: str) -> None:
        shown.append(piece)

    async def scenario() -> None:
        stream = HideSourcesLine(collect)
        for piece in ["Lunch costs 6.50", " EUR.\nSo", "urces", ": canteen", ".txt"]:
            await stream.feed(piece)
        await stream.flush()

    run(scenario())
    assert "".join(shown) == "Lunch costs 6.50 EUR.\n"


def test_chat_lists_only_the_documents_the_model_used(client, make_user, infra):
    _, email, password = make_user(["documents.list", "documents.create", "audit.list"])
    login(client, email, password)
    used = upload(client, "Meal rules", b"The meal allowance is 47 EUR per day.", "meals.txt").json()["id"]
    unused = upload(client, "Meal plan", b"The canteen meal plan changes weekly.", "plan.txt").json()["id"]
    process(used)
    process(unused)
    infra.llm.answer = "The allowance is 47 EUR per day.\nSOURCES: meals.txt"

    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
    with client.websocket_connect("/api/v1/chat/ws", headers=headers) as chat:
        chat.send_json({"type": "ask", "messages": [{"role": "user", "content": "meal allowance"}]})
        while (answer := chat.receive_json())["type"] != "answer":
            pass

    assert answer["content"] == "The allowance is 47 EUR per day."
    assert [s["id"] for s in answer["sources"]] == [used]
    read = client.get("/api/v1/audit", params={"action": "chat.answer"}).json()["items"][0]
    assert {d["id"] for d in read["details"]["documents"]} >= {used, unused}  # the audit keeps all it read


def test_hits_below_the_model_threshold_are_not_used(client, make_user, infra, monkeypatch):
    import dataclasses

    import settings
    from services.chat.chat import NO_DOCUMENTS_ANSWER

    spec = settings.EMBEDDING_MODELS["multilingual-e5-small"]
    monkeypatch.setitem(settings.EMBEDDING_MODELS, "multilingual-e5-small", dataclasses.replace(spec, min_score=0.99))
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)
    process(upload(client, "Parking", b"Visitors park in zone C.", "parking.txt").json()["id"])

    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
    with client.websocket_connect("/api/v1/chat/ws", headers=headers) as chat:
        chat.send_json({"type": "ask", "messages": [{"role": "user", "content": "Where do visitors park?"}]})
        while (answer := chat.receive_json())["type"] != "answer":
            pass

    assert answer["sources"] == [] and answer["content"] == NO_DOCUMENTS_ANSWER
    assert not any(call["stream"] for call in infra.llm.calls)  # the model is not asked


def test_a_code_in_the_question_finds_its_chunk_below_the_threshold(client, make_user, infra, monkeypatch):
    import dataclasses

    import settings

    spec = settings.EMBEDDING_MODELS["multilingual-e5-small"]
    monkeypatch.setitem(settings.EMBEDDING_MODELS, "multilingual-e5-small", dataclasses.replace(spec, min_score=0.99))
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)
    document_id = upload(client, "Assets", b"LT-3044 ThinkPad, warranty until 2027-03-14.", "assets.txt").json()["id"]
    process(document_id)
    infra.llm.answer = "The warranty ends on 2027-03-14.\nSOURCES: Assets"

    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
    with client.websocket_connect("/api/v1/chat/ws", headers=headers) as chat:
        chat.send_json({"type": "ask", "messages": [{"role": "user", "content": "When does LT-3044 expire?"}]})
        while (answer := chat.receive_json())["type"] != "answer":
            pass

    assert [source["id"] for source in answer["sources"]] == [document_id]


def test_an_answer_that_repeats_the_question_is_judged_by_all_its_words():
    from services.chat.answer_sources import support

    question = "Is alcohol paid back by the company?"
    answer = "No, the company does not pay back alcohol."
    assert support(answer, question, _doc(1, "Alcohol, fines and entertainment are never paid back.")) >= 0.2
    assert support(answer, question, _doc(2, "Visitors park in zone C.")) == 0
