"""Several interface languages (APP_LANGUAGES): each user reads errors,
notices and answers in the language they chose in the header."""

from conftest import csrf, login, process, run, upload


def test_languages_are_the_default_then_the_enabled_ones(monkeypatch):
    from exceptions import AppError
    from settings import languages

    monkeypatch.setenv("APP_LANGUAGE", "es")
    monkeypatch.delenv("APP_LANGUAGES", raising=False)
    assert languages() == ("es",)
    monkeypatch.setenv("APP_LANGUAGES", "en, fr,es")
    assert languages() == ("es", "en", "fr")
    monkeypatch.setenv("APP_LANGUAGES", "en,de")
    try:
        languages()
        raise AssertionError("an unknown language must be refused")
    except AppError as exc:
        assert exc.code == "misconfigured"


def test_signed_out_requests_follow_the_interface_language(client, monkeypatch):
    monkeypatch.setenv("APP_LANGUAGES", "en,fr")
    wrong = {"email": "nobody@acme.io", "password": "wrong-password"}

    french = client.post("/api/v1/auth/login", json=wrong, headers={"Accept-Language": "fr"})
    assert french.json()["message"] == "E-mail ou mot de passe incorrect"
    # Not enabled: the default language.
    spanish = client.post("/api/v1/auth/login", json=wrong, headers={"Accept-Language": "es-ES,es;q=0.9"})
    assert spanish.json()["message"] == "Email or password is wrong"


def test_a_users_choice_is_saved_and_wins_over_the_header(client, make_user, monkeypatch):
    monkeypatch.setenv("APP_LANGUAGES", "en,es")
    _, email, password = make_user(["documents.list"])
    login(client, email, password)
    assert client.get("/api/v1/auth/me").json()["language"] is None

    refused = client.put("/api/v1/auth/language", json={"language": "fr"}, headers=csrf(client))
    assert refused.status_code == 400  # French is not enabled
    assert client.put("/api/v1/auth/language", json={"language": "es"}, headers=csrf(client)).status_code == 204

    assert client.get("/api/v1/auth/me").json()["language"] == "es"
    missing = client.get("/api/v1/documents/999999/file", headers={"Accept-Language": "en"})
    assert missing.json()["message"] == "Documento no encontrado"


def test_the_worker_writes_errors_and_notices_in_the_owners_language(client, make_user, monkeypatch):
    monkeypatch.setenv("APP_LANGUAGES", "en,fr")
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)
    client.put("/api/v1/auth/language", json={"language": "fr"}, headers=csrf(client))

    document_id = upload(client, "Blank", b" \n \n", "blank.txt").json()["id"]
    process(document_id)

    items = client.get("/api/v1/documents").json()["items"]
    document = next(item for item in items if item["id"] == document_id)
    assert document["status"] == "failed"
    assert document["error_message"] == "Le document ne contient pas de texte."
    notices = client.get("/api/v1/notifications").json()["items"]
    assert any(note["message"] == "Le document ne contient pas de texte." for note in notices)


def test_the_assistant_answers_in_the_users_language(monkeypatch):
    from fakes import FakeOllama

    from i18n import use_language
    from schemas.chat import ChatMessageSchema
    from services.chat.generator import OllamaGenerator

    monkeypatch.setenv("APP_LANGUAGES", "en,es")
    llm = FakeOllama()

    async def ask() -> None:
        use_language("es")
        await OllamaGenerator(llm).complete([ChatMessageSchema(role="user", content="Budget?")], [])

    run(ask())  # its own context: the language does not leak into other tests
    assert "Always reply in Spanish" in llm.calls[0]["messages"][0]["content"]
