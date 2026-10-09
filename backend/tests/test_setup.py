"""`uv run setup` / `configure`: every step against a temporary .env, with
scripted answers to the terminal prompts."""

import sys
from types import SimpleNamespace

import pytest
from rich.console import Console
from rich.prompt import PromptBase

import setup.env as env_module

MODULES = (
    "setup.env",
    "setup.key",
    "setup.steps.credentials",
    "setup.steps.storage",
    "setup.steps.language",
    "setup.steps.llm",
    "setup.steps.embedding",
    "setup.steps.chunking",
    "setup.steps.chat",
    "setup.steps.key_store",
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    for name in MODULES:
        monkeypatch.setattr(sys.modules.get(name) or __import__(name, fromlist=["x"]), "ENV_PATH", path)
    return path


@pytest.fixture
def answers(monkeypatch):
    """Answers for rich prompts in order; None takes the default."""
    queue: list = []

    def ask(cls, prompt="", *, default=..., **kwargs):
        value = queue.pop(0)
        return default if value is None else value

    monkeypatch.setattr(PromptBase, "ask", classmethod(ask))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    return queue


def _console() -> Console:
    return Console(record=True, width=200)


def _values(path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#")
    )


# .env helpers


def test_env_file_helpers(env, monkeypatch):
    env.write_text('# DB_USER=commented\nDB_USER="quoted"\nDB_USER=duplicate\nOTHER=1\n')
    assert env_module.env_value(env, "DB_USER") == "quoted"
    env_module.upsert_env(env, "DB_USER", "corporate")
    env_module.upsert_env(env, "NEW_KEY", "value")
    assert env.read_text() == "# DB_USER=commented\nDB_USER=corporate\nOTHER=1\n\nNEW_KEY=value\n"
    with pytest.raises(ValueError):
        env_module.upsert_env(env, "BAD", "two words")

    tokens = iter(["-starts-with-dash", "fine"])
    monkeypatch.setattr(env_module.secrets, "token_urlsafe", lambda n: next(tokens))
    assert env_module.random_secret() == "fine"


def test_a_missing_env_file_is_created_from_the_example(env):
    env_module.ensure_env(_console())
    assert _values(env)["APP_LANGUAGE"] == "en"


# Secrets and the encryption key


def test_secrets_are_generated_and_the_key_backup_is_confirmed(env, answers):
    from encryption import key_fingerprint
    from setup.steps.credentials import SecretsStep

    env.write_text("DB_PASSWORD=password\n")
    answers.extend(["later", "saved"])  # keeps asking until the copy is confirmed
    console = _console()

    SecretsStep().run(console)

    values = _values(env)
    for key in ("JWT_SECRET_KEY", "DB_PASSWORD", "RABBITMQ_PASSWORD", "QDRANT_API_KEY", "DATA_ENCRYPTION_KEY"):
        assert len(values[key]) >= 32 and not values[key].startswith("-")
    assert values["DB_USER"] == "corporate"
    output = console.export_text()
    assert values["DATA_ENCRYPTION_KEY"] in output and key_fingerprint(values["DATA_ENCRYPTION_KEY"]) in output
    assert answers == []

    SecretsStep().run(console)  # second run changes nothing
    assert _values(env) == values and "already set" in console.export_text()


def test_minio_gets_a_root_and_a_separate_app_user(env):
    from setup.steps.storage import StorageStep

    env.write_text("MINIO_ROOT_USER=minioadmin\nMINIO_ROOT_PASSWORD=minioadmin\n")
    StorageStep().run(_console())
    values = _values(env)
    assert values["MINIO_ROOT_USER"] == "minio-root" and values["MINIO_ACCESS_KEY"] == "corporate-app"
    assert values["MINIO_SECRET_KEY"] != values["MINIO_ROOT_PASSWORD"]


def test_key_command_shows_rotates_and_refuses_a_second_rotation(env, answers, capsys):
    from encryption import key_fingerprint
    from setup.key import main as key_command

    old = "original-key-" + "o" * 32
    env.write_text(f"DATA_ENCRYPTION_KEY={old}\n")
    key_command([])
    shown = capsys.readouterr().out
    assert key_fingerprint(old) in shown and old not in shown
    key_command(["--show"])
    assert old in capsys.readouterr().out

    answers.append("saved")
    key_command(["rotate"])
    values = _values(env)
    assert values["DATA_ENCRYPTION_KEY_PREVIOUS"] == old and values["DATA_ENCRYPTION_KEY"] != old
    key_command([])
    assert "Rotation in progress" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="already in progress"):
        key_command(["rotate"])
    with pytest.raises(SystemExit):
        key_command(["unknown"])


@pytest.fixture
def vault(monkeypatch):
    """A fake Vault behind every VaultClient setup and the app create."""
    from fakes import FakeVault

    import key_store
    import setup.key
    import setup.steps.key_store as step_module

    fake = FakeVault()

    class Bound(key_store.VaultClient):
        def __init__(self, config, transport=None):
            super().__init__(config, transport or fake.transport())

    for module in (key_store, setup.key, step_module):
        monkeypatch.setattr(module, "VaultClient", Bound)
    return fake


# Answers to the Vault questions: CA file, address, role_id, secret_id, mount, path.
VAULT_ANSWERS = ["", "https://vault.test:8200", "corpus-role", "corpus-secret", None, None]


def test_the_key_moves_into_vault_rotates_there_and_moves_back(env, answers, vault):
    from encryption import key_fingerprint
    from setup.key import main as key_command
    from setup.steps.credentials import SecretsStep
    from setup.steps.key_store import KeyStoreStep

    key = "original-key-" + "o" * 32
    env.write_text(f"DATA_ENCRYPTION_KEY={key}\n")
    answers.extend([2, *VAULT_ANSWERS, "admin-token"])

    KeyStoreStep().run(_console())

    assert vault.secrets["corpus"] == {"DATA_ENCRYPTION_KEY": key}
    values = _values(env)
    assert "DATA_ENCRYPTION_KEY" not in values  # a copy of the disk holds no key
    assert (values["KEY_STORE"], values["VAULT_ADDR"], values["VAULT_KV_PATH"]) == (
        "vault",
        "https://vault.test:8200",
        "corpus",
    )
    console = _console()
    SecretsStep().run(console)  # must not make a second key in .env
    assert "DATA_ENCRYPTION_KEY" not in _values(env)

    answers.extend(["admin-token", "saved"])
    key_command(["rotate"])
    rotated = vault.secrets["corpus"]
    assert rotated["DATA_ENCRYPTION_KEY_PREVIOUS"] == key and rotated["DATA_ENCRYPTION_KEY"] != key
    answers.append("admin-token")
    key_command(["finish"])
    assert vault.secrets["corpus"] == {"DATA_ENCRYPTION_KEY": rotated["DATA_ENCRYPTION_KEY"]}
    assert all(token in {"app-token", "admin-token", None} for _, _, token in vault.requests)

    answers.append(1)
    console = _console()
    KeyStoreStep().run(console)
    values = _values(env)
    assert values["DATA_ENCRYPTION_KEY"] == rotated["DATA_ENCRYPTION_KEY"] and values["KEY_STORE"] == "env"
    assert not any(name.startswith("VAULT_") for name in values)  # the AppRole secret goes too
    assert key_fingerprint(rotated["DATA_ENCRYPTION_KEY"]) in console.export_text()


@pytest.mark.parametrize(
    ("stored", "answers_after", "reason"),
    [
        ({"DATA_ENCRYPTION_KEY": "someone-elses-key-" + "x" * 32}, [], "another key"),
        (None, ["", "https://vault.test:8200", "corpus-role", "wrong-secret", None, None], "invalid role"),
    ],
)
def test_nothing_changes_when_vault_cannot_take_the_key(env, answers, vault, stored, answers_after, reason):
    from setup.steps.key_store import KeyStoreStep

    if stored:
        vault.secrets["corpus"] = stored
    before = "DATA_ENCRYPTION_KEY=" + "k" * 40 + "\n"
    env.write_text(before)
    answers.extend([2, *(answers_after or VAULT_ANSWERS)])
    console = _console()

    KeyStoreStep().run(console)

    output = console.export_text()
    assert "Nothing changed" in output and reason in output
    assert env.read_text() == before and vault.secrets.get("corpus") == stored


def test_key_command_needs_a_key(env):
    from setup.key import main as key_command

    env.write_text("")
    with pytest.raises(SystemExit, match="not set"):
        key_command([])


# Choices


def test_language_step(env, answers):
    from setup.steps.language import LanguageStep

    answers.extend([False, 9, 3])  # one language: out of range, then French
    LanguageStep().run(_console())
    assert (_values(env)["APP_LANGUAGE"], _values(env)["APP_LANGUAGES"]) == ("fr", "fr")

    # Several: at least two, then the default among them.
    answers.extend([True, "2", "9,1", "1,2", 2])
    LanguageStep().run(_console())
    assert (_values(env)["APP_LANGUAGE"], _values(env)["APP_LANGUAGES"]) == ("es", "es,en")

    answers.extend([None, None, None])  # the defaults keep the choice
    LanguageStep().run(_console())
    assert (_values(env)["APP_LANGUAGE"], _values(env)["APP_LANGUAGES"]) == ("es", "es,en")


def test_several_languages_offer_models_for_all_of_them():
    from setup.steps import embedding, llm

    assert [option.key for option in embedding.options_for(["en", "fr"])] == [
        "multilingual-e5-small",
        "multilingual-e5-base",
        "bge-m3",
    ]
    assert [option.key for option in embedding.options_for(["en"])][0] == "bge-small-en"
    assert llm.options_for(["en", "es", "fr"]) == llm.OPTIONS["en"]


def test_chat_capacity_step(env, answers):
    from setup.steps.chat import ChatStep

    env.write_text("LLM_MODEL=llama3.1:8b\nLLM_NUM_CTX=16384\n")
    answers.extend([5000, 30, 0, 2])  # out-of-range answers are asked again
    console = _console()

    ChatStep().run(console)

    values = _values(env)
    assert values["CHAT_QUESTIONS_PER_10_MIN"] == "30" and values["LLM_PARALLEL"] == "2"
    assert "up to 2.1 GB" in console.export_text()  # 2 answers x 16k context of llama3.1:8b


def test_chunking_presets_custom_sizes_and_the_model_limit_warning(env, answers, monkeypatch):
    import setup.steps.chunking as chunking

    env.write_text("EMBEDDING_MODEL=multilingual-e5-small\n")
    monkeypatch.setattr(chunking, "_input_limits", lambda spec: {"en": 900})
    answers.extend([1])  # Precise
    chunking.ChunkingStep().run(_console())
    assert (_values(env)["CHUNK_SIZE"], _values(env)["CHUNK_OVERLAP"]) == ("400", "80")

    # Broad (1200 + 200) is longer than the model reads: declined, then custom.
    answers.extend([3, False, 4, 700, 500, 100])
    chunking.ChunkingStep().run(_console())
    assert (_values(env)["CHUNK_SIZE"], _values(env)["CHUNK_OVERLAP"]) == ("700", "100")
    assert chunking._estimate(800, 150, 384)[0] == 385


class _FakeOllamaClient:
    def __init__(self, installed: set[str]) -> None:
        self.installed = installed
        self.pulled: list[str] = []

    def list(self):
        return SimpleNamespace(models=[SimpleNamespace(model=m) for m in self.installed])

    def pull(self, tag, stream=True):
        self.pulled.append(tag)
        yield SimpleNamespace(status="downloading", total=10, completed=10)


def test_llm_step_keeps_a_downloaded_model_and_pulls_a_custom_one(env, answers, monkeypatch):
    import setup.steps.llm as llm

    client = _FakeOllamaClient({"llama3.1:8b"})
    monkeypatch.setattr(llm, "_client", lambda: client)
    env.write_text("APP_LANGUAGE=en\n")

    answers.extend([1])
    llm.LlmStep().run(_console())
    assert _values(env)["LLM_MODEL"] == "llama3.1:8b" and client.pulled == []

    answers.extend([4, "mistral:7b"])
    llm.LlmStep().run(_console())
    assert _values(env)["LLM_MODEL"] == "mistral:7b" and client.pulled == ["mistral:7b"]


@pytest.mark.parametrize(("points", "locked"), [(None, True), (12, True), (0, False)])
def test_embedding_model_is_locked_while_documents_are_indexed(env, answers, monkeypatch, points, locked):
    import setup.steps.embedding as embedding

    env.write_text("APP_LANGUAGE=en\nEMBEDDING_MODEL=multilingual-e5-base\n")
    downloaded: list[str] = []
    monkeypatch.setattr(embedding, "_rag_points", lambda: points)
    monkeypatch.setattr(embedding, "_cached", lambda hf_id: False)
    monkeypatch.setattr(embedding, "snapshot_download", downloaded.append)
    answers.extend([1])

    embedding.EmbeddingStep().run(_console())

    changed = _values(env)["EMBEDDING_MODEL"] != "multilingual-e5-base"
    assert changed is not locked and bool(downloaded) is not locked


def test_setup_and_configure_run_their_steps(env, answers, monkeypatch, capsys):
    import configure
    import setup.app as app

    ran: list[list[str]] = []
    monkeypatch.setattr(configure, "run", lambda steps, *a, **k: ran.append([s.title for s in steps]))
    configure.main()
    assert ran == [["System language", "LLM model", "Chat capacity", "Chunk size", "Encryption key storage"]]

    env.write_text("DATA_ENCRYPTION_KEY=" + "k" * 40 + "\n")
    monkeypatch.setattr(sys, "argv", ["setup", "key"])
    app.main()
    assert "Fingerprint:" in capsys.readouterr().out

    step = SimpleNamespace(title="Only", run=lambda console: console.print("step ran"))
    app.run([step], "Done.", footer="Restart now.")
    output = capsys.readouterr().out
    assert "step ran" in output and "Done." in output and "Restart now." in output
