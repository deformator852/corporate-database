"""Operator commands: key rotation over every store, backup encryption,
first administrator, model download, seeders."""

import os
import subprocess
import sys
from pathlib import Path

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

        assert all(is_current_bytes(blob) for blob in infra.minio.objects.values())
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
        input=stdin, capture_output=True, cwd=SRC, env=env, timeout=60,
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


def test_first_administrator_is_created_once(capsys, monkeypatch):
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


def test_model_download_fetches_the_configured_embedding_model(monkeypatch, capsys):
    from maintenance import download_models

    fetched: list[str] = []
    monkeypatch.setattr(download_models, "snapshot_download", lambda repo: fetched.append(repo) or "/models/x")
    download_models.main()
    assert fetched == ["intfloat/multilingual-e5-small"] and "ready in /models/x" in capsys.readouterr().out


def test_seeders_prepare_permissions_roles_and_the_search_collection(infra):
    from seeders.run import main as seed

    run(seed())
    run(seed())  # idempotent
    assert run(infra.qdrant.collection_exists("documents"))
