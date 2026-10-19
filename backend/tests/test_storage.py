"""Document files: on disk (the default) or in the company's own S3 storage
(STORAGE=s3), encrypted either way."""

import pytest
from conftest import csrf, login, process, run, upload

WRITER = ["documents.list", "documents.create", "documents.delete", "system.view"]
TEXT = b"The travel budget per trip is 500 EUR."


@pytest.fixture
def s3(monkeypatch):
    """STORAGE=s3 against a stand-in storage; returns it."""
    from fakes import FakeMinio

    import services.storage as storage

    fake = FakeMinio()
    made: list[dict] = []

    def client(endpoint, **kwargs):
        made.append({"endpoint": endpoint, **kwargs})
        return fake

    monkeypatch.setattr(storage, "Minio", client)
    monkeypatch.setenv("STORAGE", "s3")
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.acme.io:9443")
    monkeypatch.setenv("S3_BUCKET", "corpus")
    monkeypatch.setenv("S3_ACCESS_KEY", "corpus-app")
    monkeypatch.setenv("S3_SECRET_KEY", "s3-secret-" + "x" * 20)
    fake.made = made
    return fake


def test_files_on_disk_are_encrypted_private_and_never_half_written(client, make_user, infra):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel", TEXT, "travel.txt").json()["id"]

    [path] = [p for p in infra.files.root.rglob("*") if p.is_file()]
    assert b"500 EUR" not in path.read_bytes() and path.name != "travel.txt"  # no name either
    assert path.stat().st_mode & 0o777 == 0o600
    assert client.get(f"/api/v1/documents/{document_id}/file").content == TEXT
    assert not list(infra.files.root.rglob("*.tmp"))


def test_a_file_key_cannot_leave_the_folder(tmp_path):
    from exceptions import AppError
    from services.storage import DiskStore

    with pytest.raises(AppError):
        DiskStore(tmp_path / "files").read("../outside")


def test_documents_go_to_the_companys_s3_storage(client, make_user, infra, s3):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel", TEXT, "travel.txt").json()["id"]
    process(document_id)

    [(key, stored)] = s3.objects.items()
    assert key.startswith("documents/") and b"500 EUR" not in stored  # encrypted, no name
    assert infra.files.all() == []
    assert s3.made[0]["endpoint"] == "s3.acme.io:9443" and s3.made[0]["secure"] is True
    assert client.get(f"/api/v1/documents/{document_id}/file").content == TEXT
    services = {s["name"]: s for s in client.get("/api/v1/system/status").json()["services"]}
    assert services["storage"] == {"name": "storage", "status": "ok", "detail": "Bucket corpus at s3.acme.io:9443"}

    assert client.delete(f"/api/v1/documents/{document_id}", headers=csrf(client)).status_code == 204
    assert s3.objects == {}


def test_key_rotation_re_encrypts_the_files_in_s3(client, make_user, infra, s3, monkeypatch):
    import os

    from conftest import run

    import encryption
    from encryption import is_current_bytes
    from maintenance.rotate_key import reencrypt_all

    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel", TEXT, "travel.txt").json()["id"]
    [before] = s3.objects.values()
    old_key = os.environ["DATA_ENCRYPTION_KEY"]
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "rotated-encryption-key-" + "s" * 32)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_PREVIOUS", old_key)
    encryption.reset_keys()
    try:
        run(reencrypt_all(lambda _: None))
        [after] = s3.objects.values()
        assert after != before and is_current_bytes(after)
        monkeypatch.delenv("DATA_ENCRYPTION_KEY_PREVIOUS")
        encryption.reset_keys()  # the old key is gone; the file still opens
        assert client.get(f"/api/v1/documents/{document_id}/file").content == TEXT
    finally:
        monkeypatch.setenv("DATA_ENCRYPTION_KEY", old_key)
        monkeypatch.setenv("DATA_ENCRYPTION_KEY_PREVIOUS", "rotated-encryption-key-" + "s" * 32)
        encryption.reset_keys()
        run(reencrypt_all(lambda _: None))
        monkeypatch.delenv("DATA_ENCRYPTION_KEY_PREVIOUS")
        encryption.reset_keys()


def _storage_status(client) -> dict:
    return next(s for s in client.get("/api/v1/system/status").json()["services"] if s["name"] == "storage")


def test_a_refusing_s3_storage_shows_on_the_status_page(client, make_user, infra, s3):
    _, email, password = make_user(WRITER)
    login(client, email, password)
    upload(client, "Travel", TEXT, "travel.txt")
    s3.fail_with = "AccessDenied"

    assert _storage_status(client) == {
        "name": "storage",
        "status": "down",
        "detail": "The S3 storage refused Corpus: AccessDenied (bucket corpus at s3.acme.io:9443).",
    }
    assert upload(client, "Other", b"Other text.", "other.txt").json()["message"] == "Could not store the document."


def test_amazon_s3_without_list_rights_is_not_shown_as_down(client, make_user, infra, s3):
    """The account may only get, put and delete objects: Amazon S3 then
    answers AccessDenied for any missing object, the status probe's too."""
    s3.missing_code = "AccessDenied"
    _, email, password = make_user(WRITER)
    login(client, email, password)
    assert _storage_status(client)["status"] == "ok"  # no documents yet

    upload(client, "Travel", TEXT, "travel.txt")
    assert _storage_status(client)["status"] == "ok"  # reads a real file
    s3.objects.clear()  # the file is gone: down, as AccessDenied there too
    assert _storage_status(client)["status"] == "down"
    s3.missing_code = "NoSuchKey"  # storages that say so
    assert _storage_status(client)["detail"] == (
        "A document file is missing from the S3 storage (bucket corpus at s3.acme.io:9443)."
    )


def test_a_reply_that_is_not_s3_is_an_outage_not_a_crash(client, make_user, infra, s3, monkeypatch):
    """A proxy's HTML error page in front of the storage, say."""
    from minio.error import InvalidResponseError

    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel", TEXT, "travel.txt").json()["id"]

    def proxy_page(*args, **kwargs):
        raise InvalidResponseError(502, "text/html", "<html>Bad gateway</html>")

    monkeypatch.setattr(s3, "get_object", proxy_page)
    response = client.get(f"/api/v1/documents/{document_id}/file")
    assert response.status_code == 503 and response.json()["message"] == "Could not read the document."


def test_production_reaches_the_s3_storage_through_its_tunnel():
    """The internal network has no route out: every request dials s3-tunnel,
    while the certificate is still checked against the storage's own name."""
    from services.storage import _http_client
    from settings import S3Config

    config = S3Config("https://s3.acme.io", "corpus", "a", "s", connect="s3-tunnel:9000")
    pool = _http_client(config).connection_from_host("s3.acme.io", 443, scheme="https")
    assert (pool.host, pool.port) == ("s3-tunnel", 9000)
    assert pool.assert_hostname == "s3.acme.io" and pool.conn_kw["server_hostname"] == "s3.acme.io"

    direct = _http_client(S3Config("https://s3.acme.io", "corpus", "a", "s"))
    assert direct.connection_from_host("s3.acme.io", 443, scheme="https").host == "s3.acme.io"


def test_s3_settings_are_checked(monkeypatch):
    from exceptions import AppError
    from settings import s3_config, storage

    monkeypatch.setenv("STORAGE", "tape")
    with pytest.raises(AppError):
        storage()
    for endpoint in ("s3.acme.io", "https://s3.acme.io/bucket"):
        monkeypatch.setenv("S3_ENDPOINT", endpoint)
        with pytest.raises(AppError):
            s3_config()


def _file_missing(client, document_id: int) -> bool:
    items = client.get("/api/v1/documents", params={"per_page": 100}).json()["items"]
    return next(item["file_missing"] for item in items if item["id"] == document_id)


def test_files_move_to_another_storage_once_and_still_decrypt(client, make_user, infra):
    from fakes import FakeMinio

    from maintenance.move_files import document_keys, move
    from services.storage import DiskStore, ObjectStorage, S3Store
    from settings import S3Config

    _, email, password = make_user(WRITER)
    login(client, email, password)
    upload(client, "Travel", TEXT, "travel.txt")
    upload(client, "Leave", b"Leave requests go to HR.", "leave.txt")
    keys = run(document_keys())  # in upload order
    infra.files.remove(keys[1])  # gone from the old storage too
    target = S3Store(S3Config("https://s3.acme.io", "corpus", "corpus-app", "secret"), client=FakeMinio())

    moved = move(keys, DiskStore(infra.files.root), target, lambda _: None)

    assert (moved.copied, moved.present, moved.missing) == (1, 0, 1)
    assert ObjectStorage(target).get(keys[0]) == TEXT  # same key, same encryption
    again = move(keys, DiskStore(infra.files.root), target, lambda _: None)  # resumed: nothing copied twice
    assert (again.copied, again.present, again.missing) == (0, 1, 1)


def test_documents_without_a_file_are_marked_when_the_backend_starts(client, make_user, infra):
    from database import AsyncSessionLocal
    from services.documents.file_check import mark_missing_files
    from services.storage import file_store

    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel", TEXT, "travel.txt").json()["id"]
    process(document_id)

    async def check() -> int:
        async with AsyncSessionLocal() as session:
            return await mark_missing_files(session, file_store())

    assert run(check()) == 0 and not _file_missing(client, document_id)
    [key] = [path.relative_to(infra.files.root).as_posix() for path in infra.files.root.rglob("*") if path.is_file()]
    content = infra.files.get(key)
    infra.files.remove(key)  # another storage configured, or deleted by hand
    assert run(check()) == 1 and _file_missing(client, document_id)
    assert client.get("/api/v1/system/status").json()["missing_files"] == 1
    assert client.get(f"/api/v1/documents/{document_id}/file").status_code == 503

    (infra.files.root / key).write_bytes(content)  # copied back
    assert run(check()) == 0 and not _file_missing(client, document_id)


def test_a_ready_document_whose_file_is_gone_is_kept_when_reindexed(client, make_user, infra):
    """Re-embedding (another model) with the files in another storage: the
    documents fail, marked, and can be retried; they are not deleted."""
    from sqlalchemy import update

    from database import AsyncSessionLocal
    from models.document import Document, DocumentStatus
    from services.documents.processor import drop_incomplete_document_job

    _, email, password = make_user(WRITER)
    login(client, email, password)
    document_id = upload(client, "Travel", TEXT, "travel.txt").json()["id"]
    process(document_id)

    async def queue_again() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Document).where(Document.id == document_id).values(status=DocumentStatus.QUEUED, reindexing=True)
            )
            await session.commit()

    run(queue_again())
    run(drop_incomplete_document_job(document_id))  # the worker's last retry found no file

    [item] = [i for i in client.get("/api/v1/documents").json()["items"] if i["id"] == document_id]
    assert (item["status"], item["file_missing"]) == ("failed", True)
    assert item["error_message"] == "The document file is missing."
