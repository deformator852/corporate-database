"""Operator commands: key rotation over every store, backup encryption,
first administrator, model download, seeders."""

import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import login, process, run, upload

SRC = Path(__file__).resolve().parent.parent / "src"
NEW_KEY = "rotated-encryption-key-" + "n" * 32


def test_rotation_reencrypts_files_texts_and_search_chunks(client, make_user, infra, monkeypatch):
    import encryption
    from encryption import current_fingerprint, is_current_bytes, is_current_text
    from maintenance.rotate_key import reencrypt_all
    from services.encryption_key import stored_fingerprint

    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)
    document_id = upload(client, "Payroll", b"Salaries are paid on the 25th.", "payroll.txt").json()["id"]
    process(document_id)
    old_key = os.environ["DATA_ENCRYPTION_KEY"]
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", NEW_KEY)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_PREVIOUS", old_key)
    encryption.reset_keys()
    report: list[str] = []
    try:
        run(reencrypt_all(report.append))

        files = infra.files.all()
        assert files and all(is_current_bytes(blob) for blob in files)
        points, _ = run(infra.qdrant.scroll("documents", limit=1000, with_payload=True))
        assert points and all(is_current_text(p.payload["text"]) for p in points)
        assert report[-1] == "Done: all data is encrypted with the current key."

        async def fingerprint():
            from database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                return await stored_fingerprint(session)

        assert run(fingerprint()) == current_fingerprint()
        monkeypatch.delenv("DATA_ENCRYPTION_KEY_PREVIOUS")
        encryption.reset_keys()  # the old key is gone; everything still opens
        assert client.get(f"/api/v1/documents/{document_id}/file").content == b"Salaries are paid on the 25th."
    finally:
        # Rotate back, so later tests run with the usual test key.
        monkeypatch.setenv("DATA_ENCRYPTION_KEY", old_key)
        monkeypatch.setenv("DATA_ENCRYPTION_KEY_PREVIOUS", NEW_KEY)
        encryption.reset_keys()
        run(reencrypt_all(lambda _: None))
        monkeypatch.delenv("DATA_ENCRYPTION_KEY_PREVIOUS")
        encryption.reset_keys()


def test_switching_the_embedding_model_embeds_every_document_again(client, make_user, infra, monkeypatch):
    import pytest

    from database import AsyncSessionLocal
    from exceptions import AppError
    from maintenance.switch_embedding import switch
    from services.search import embedding
    from services.search.index_model import outdated_index_model, save_index_model, stored_index_model

    old_model = os.environ["EMBEDDING_MODEL"]
    monkeypatch.setenv("EMBEDDING_MODEL", old_model)  # restored after the test; switch() sets it
    _, email, password = make_user(["documents.list", "documents.create"])
    login(client, email, password)
    document_id = upload(client, "Payroll", b"Salaries are paid on the 25th.", "payroll.txt").json()["id"]
    process(document_id)
    notices = len(client.get("/api/v1/notifications").json()["items"])

    async def index_model() -> str | None:
        async with AsyncSessionLocal() as session:
            return await stored_index_model(session)

    async def outdated() -> str | None:
        async with AsyncSessionLocal() as session:
            return await outdated_index_model(session)

    def points() -> int:
        if not run(infra.qdrant.collection_exists("documents")):
            return 0
        return run(infra.qdrant.count("documents")).count

    def status() -> str:
        return client.get("/api/v1/documents").json()["items"][0]["status"]

    try:
        # A model that is not on disk changes nothing.
        class Missing:
            def __init__(self, model_id: str) -> None:
                raise OSError("not downloaded")

        fake = embedding.SentenceTransformer
        monkeypatch.setattr(embedding, "SentenceTransformer", Missing)
        with pytest.raises(AppError, match="that it is downloaded"):
            run(switch("bge-small-en", lambda _: None))
        assert (points() > 0, status(), run(index_model())) == (True, "completed", old_model)
        monkeypatch.setattr(embedding, "SentenceTransformer", fake)
        monkeypatch.setenv("EMBEDDING_MODEL", old_model)

        report: list[str] = []
        assert run(switch("bge-small-en", report.append)) >= 1

        assert points() == 0 and status() == "queued"
        assert run(index_model()) == "bge-small-en"
        assert run(outdated()) is None  # EMBEDDING_MODEL now names the index's model
        headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
        with client.websocket_connect("/api/v1/system/reindex/ws", headers=headers) as banner:
            assert banner.receive_json() == {"active": True, "percent": 0}  # every user's banner, at once
            process(document_id)  # what the worker does when it starts
            # Pushed as the document moves on, until the switch is over.
            seen = [banner.receive_json()]
            while seen[-1]["active"]:
                seen.append(banner.receive_json())
        assert seen[-1] == {"active": False, "percent": 100}
        assert points() > 0 and status() == "completed"
        # Ready before: no "is ready" notice for it again.
        assert len(client.get("/api/v1/notifications").json()["items"]) == notices

        monkeypatch.setenv("EMBEDDING_MODEL", old_model)  # .env edited by hand
        assert run(outdated()) == "bge-small-en"
        with pytest.raises(AppError, match="Unknown embedding model"):
            run(switch("no-such-model", lambda _: None))
    finally:

        async def restore() -> None:
            async with AsyncSessionLocal() as session:
                await save_index_model(session, old_model)

        run(restore())


def _switch_embedding_model_command(monkeypatch, tmp_path, *, production: bool):
    """switch_embedding_model with its .env in tmp_path and the running stack faked."""
    import switch_embedding_model

    env = tmp_path / ".env"
    env.write_text("EMBEDDING_MODEL=multilingual-e5-small\n")
    monkeypatch.setattr(switch_embedding_model, "ENV_PATH", env)
    monkeypatch.setattr(switch_embedding_model, "production_running", lambda: production)
    monkeypatch.setattr(sys, "argv", ["switch-embedding-model", "bge-small-en"])
    return switch_embedding_model, env


def test_switch_embedding_model_in_production_downloads_stops_rebuilds_and_starts(monkeypatch, tmp_path):
    steps: list[tuple[str, ...]] = []
    command, env = _switch_embedding_model_command(monkeypatch, tmp_path, production=True)
    monkeypatch.setattr(command, "compose", lambda *args, **kwargs: steps.append(args) or "")

    command.main()

    assert [step[:4] for step in steps] == [
        ("--profile", "setup", "run", "--rm"),  # download first: needs the internet
        ("stop", "backend", "worker"),
        ("run", "--rm", "--no-deps", "-e"),
        ("up", "-d", "backend", "worker"),
    ]
    assert steps[0][-2:] == ("EMBEDDING_MODEL=bge-small-en", "models")
    assert steps[2][-4:] == ("python", "-m", "maintenance.switch_embedding", "bge-small-en")
    assert "EMBEDDING_MODEL=bge-small-en" in env.read_text()


def test_switch_embedding_model_finds_production_while_the_backend_restarts(monkeypatch):
    # The backend of a stack whose model does not match the index restarts in
    # a loop; its database runs.
    import switch_embedding_model as command

    running = {"postgres"}
    monkeypatch.setattr(command, "compose", lambda *args, **kwargs: "id\n" if args[-1] in running else "")
    assert command.production_running()
    running.clear()
    assert not command.production_running()


def test_compose_reads_env_from_the_file_not_from_what_was_loaded_earlier(monkeypatch, tmp_path):
    import switch_embedding_model as command

    env_file = tmp_path / ".env"
    env_file.write_text("EMBEDDING_MODEL=multilingual-e5-base\nDB_USER=corporate\n")
    monkeypatch.setattr(command, "ENV_PATH", env_file)
    # Loaded at start, before the switch wrote the new model to the file.
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-base-en")
    seen: dict[str, str] = {}
    monkeypatch.setattr(command.subprocess, "run", lambda *a, env, **k: seen.update(env) or SimpleNamespace(stdout=""))

    command.compose("up", "-d", "backend", "worker")

    # Compose prefers the environment to --env-file: the stale value must not reach it.
    assert "EMBEDDING_MODEL" not in seen and "DB_USER" not in seen
    assert seen["PATH"] == os.environ["PATH"]


def test_switch_embedding_model_starts_the_old_model_again_when_the_rebuild_fails(monkeypatch, tmp_path):
    steps: list[tuple[str, ...]] = []
    command, env = _switch_embedding_model_command(monkeypatch, tmp_path, production=True)

    def compose(*args, **kwargs):
        steps.append(args)
        if args[0] == "run" and "backend" in args:
            raise subprocess.CalledProcessError(1, ["docker", "compose", *args])
        return ""

    monkeypatch.setattr(command, "compose", compose)
    with pytest.raises(SystemExit, match="Stopped"):
        command.main()

    assert steps[-1] == ("up", "-d", "backend", "worker")  # back up, with the index's own model
    assert "EMBEDDING_MODEL=multilingual-e5-small" in env.read_text()


def test_switch_embedding_model_in_development_stops_only_this_projects_backend_and_worker(monkeypatch, tmp_path):
    import maintenance.switch_embedding as rebuild

    calls: list[str] = []
    command, env = _switch_embedding_model_command(monkeypatch, tmp_path, production=False)
    # Programs named like the real ones: ours in backend/, another project's elsewhere.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("uvicorn", "celery"):
        script = fake_bin / name
        script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")  # argv like the real ones
        script.chmod(0o755)
    ours = [
        subprocess.Popen([str(fake_bin / "uvicorn"), "src.main:app", "--reload"], cwd=command.BACKEND_DIR),
        subprocess.Popen([str(fake_bin / "celery"), "-A", "worker", "worker"], cwd=command.BACKEND_DIR / "src"),
    ]
    other = subprocess.Popen([str(fake_bin / "uvicorn"), "main:app"], cwd=tmp_path)
    time.sleep(0.3)

    def load_model(model, report):
        calls.append("load")
        assert all(process.poll() is None for process in ours)  # nothing stopped yet

    async def switch(model, report):
        calls.append("switch")
        assert all(process.wait(timeout=5) is not None for process in ours)
        return 1

    monkeypatch.setattr(rebuild, "load_model", load_model)
    monkeypatch.setattr(rebuild, "switch", switch)
    try:
        command.main()
        assert calls == ["load", "switch"]
        assert other.poll() is None  # another project's uvicorn keeps running
        assert "EMBEDDING_MODEL=bge-small-en" in env.read_text()
    finally:
        for process in (*ours, other):
            process.kill()
            process.wait()


def test_switch_embedding_model_lists_models_and_where_to_find_more(monkeypatch, tmp_path, capsys):
    command, env = _switch_embedding_model_command(monkeypatch, tmp_path, production=True)
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(sys, "argv", ["switch-embedding-model", "no-such-model"])
    with pytest.raises(SystemExit):
        command.main()
    shown = capsys.readouterr().out
    assert "Unknown embedding model 'no-such-model'" in shown
    assert "https://huggingface.co/BAAI/bge-m3" in shown  # each model's card
    assert "documentations/deployment.md" in shown and "mteb/leaderboard" in shown  # details, and other models
    assert env.read_text() == "EMBEDDING_MODEL=multilingual-e5-small\n"  # nothing changed

    monkeypatch.setattr(sys, "argv", ["switch-embedding-model"])
    with pytest.raises(SystemExit):
        command.main()
    shown = capsys.readouterr().out
    assert "Usage: uv run switch-embedding-model MODEL" in shown
    assert "Current model: multilingual-e5-small" in shown  # from .env


def test_rotation_refuses_keys_that_do_not_belong_to_the_data(infra, monkeypatch):
    import encryption
    from database import AsyncSessionLocal
    from exceptions import AppError
    from maintenance.rotate_key import reencrypt_all
    from services.encryption_key import verify_encryption_key

    async def record_test_key() -> None:
        async with AsyncSessionLocal() as session:
            await verify_encryption_key(session)

    run(record_test_key())
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", NEW_KEY)
    encryption.reset_keys()
    try:
        with pytest.raises(AppError, match="neither DATA_ENCRYPTION_KEY"):
            run(reencrypt_all(lambda _: None))
    finally:
        monkeypatch.undo()
        encryption.reset_keys()


def _crypt(*args: str, stdin: bytes, key: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    if key:
        env["DATA_ENCRYPTION_KEY"] = key
    return subprocess.run(
        [sys.executable, "-m", "maintenance.backup_crypt", *args],
        input=stdin,
        capture_output=True,
        cwd=SRC,
        env=env,
        timeout=60,
    )


def test_backup_stream_command_roundtrip():
    dump = os.urandom(3 * 1024 * 1024) + b"pg_dump tail"

    sealed = _crypt("encrypt", stdin=dump)
    assert sealed.returncode == 0 and b"pg_dump tail" not in sealed.stdout

    fingerprint = _crypt("fingerprint", stdin=sealed.stdout)
    from encryption import current_fingerprint

    assert fingerprint.stdout.decode().strip() == current_fingerprint()
    assert _crypt("decrypt", stdin=sealed.stdout).stdout == dump
    refused = _crypt("decrypt", stdin=sealed.stdout, key=NEW_KEY)
    assert refused.returncode != 0 and b"set it as DATA_ENCRYPTION_KEY" in refused.stderr
    assert _crypt("nonsense", stdin=b"").returncode != 0


def test_first_administrator_is_created_once(capsys, monkeypatch, infra):  # infra: the app starts below
    from maintenance import create_admin

    monkeypatch.setattr(sys, "argv", ["create_admin", "Chief@Acme.io", "Marta", "Ruiz"])
    create_admin.main()
    printed = capsys.readouterr().out
    assert "Administrator chief@acme.io created" in printed
    password = printed.rsplit(": ", 1)[1].strip()

    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app, base_url="https://testserver") as fresh:
        assert login(fresh, "chief@acme.io", password).status_code == 200
        assert "roles.delete" in fresh.get("/api/v1/auth/me").json()["permissions"]

    with pytest.raises(SystemExit, match="already exists"):
        create_admin.main()
    monkeypatch.setattr(sys, "argv", ["create_admin", "not-an-email"])
    with pytest.raises(SystemExit):
        create_admin.main()
    monkeypatch.setattr(sys, "argv", ["create_admin", "root@corp.invalid"])  # still a reserved name
    with pytest.raises(SystemExit, match="Invalid email"):
        create_admin.main()


def test_an_internal_company_local_address_signs_in(capsys, monkeypatch, infra):
    from fastapi.testclient import TestClient

    import main
    from maintenance import create_admin

    # Active Directory domains are often company.local, reserved for mDNS.
    monkeypatch.setattr(sys, "argv", ["create_admin", "It.Admin@Company.Local"])
    create_admin.main()
    password = capsys.readouterr().out.rsplit(": ", 1)[1].strip()

    with TestClient(main.app, base_url="https://testserver") as fresh:
        assert login(fresh, "it.admin@company.local", password).status_code == 200


def test_model_download_fetches_the_configured_embedding_model(monkeypatch, capsys):
    from huggingface_hub.errors import LocalEntryNotFoundError

    from maintenance import download_models

    fetched: list[str] = []
    on_disk: set[str] = set()

    def snapshot_download(repo, local_files_only=False):
        if local_files_only:
            if repo not in on_disk:
                raise LocalEntryNotFoundError("not cached")
            return "/models/x"
        fetched.append(repo)
        on_disk.add(repo)
        return "/models/x"

    monkeypatch.setattr(download_models, "snapshot_download", snapshot_download)
    # deploy.sh up checks first, offline, and downloads only what is missing.
    with pytest.raises(SystemExit, match="not downloaded"):
        download_models.main(["--check"])
    download_models.main([])
    assert fetched == ["intfloat/multilingual-e5-small"] and "ready in /models/x" in capsys.readouterr().out
    download_models.main(["--check"])
    assert "is downloaded" in capsys.readouterr().out


def test_seeders_prepare_permissions_roles_and_the_search_collection(infra):
    from seeders.run import main as seed

    run(seed())
    run(seed())  # idempotent
    assert run(infra.qdrant.collection_exists("documents"))
