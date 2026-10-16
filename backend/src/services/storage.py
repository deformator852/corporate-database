"""Document files, encrypted (encryption.py) and bound to their key, so a
file moved to another key does not decrypt.

STORAGE=disk (default): files under STORAGE_DIR on this server; production
mounts the documents_data volume there. STORAGE=s3: the company's own
S3-compatible storage (settings.S3Config). Either way a file's key is
`documents/<uuid>`, with no filename: listing the folder or the bucket
reveals no document names. Moving between the two is copying the files under
the same keys: they are encrypted already.
"""

import contextlib
import io
import os
import uuid
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import certifi
import urllib3
from minio import Minio
from minio.error import MinioException, S3Error
from urllib3.util import Retry, Timeout

from encryption import decrypt_bytes, encrypt_bytes
from exceptions import AppError
from settings import S3Config, s3_config, storage, storage_dir

_MISSING_OBJECT = frozenset({"NoSuchKey", "NoSuchObject"})
# A key that never exists, for a status check before any document is stored.
_PROBE_KEY = "health-check/none"
# Anything the S3 client raises besides an S3 error answer: a non-S3 reply (a
# proxy's error page), a dropped connection, retries used up.
_TRANSPORT_ERRORS = (MinioException, OSError, urllib3.exceptions.HTTPError)


def _missing() -> AppError:
    # 503, and "not_found" for the worker: after its retries it drops the document.
    return AppError("not_found", "The document file is missing.", status_code=503)


def _unreadable() -> AppError:
    return AppError("unavailable", "Could not read the document.", status_code=503)


def _unstorable() -> AppError:
    return AppError("unavailable", "Could not store the document.", status_code=503)


def _undeletable() -> AppError:
    return AppError("unavailable", "Could not delete the document file.", status_code=503)


class FileStore(Protocol):
    """Where the encrypted bytes go; ObjectStorage encrypts them."""

    def read(self, key: str) -> bytes: ...

    def write(self, key: str, data: bytes) -> None: ...

    def remove(self, key: str) -> None: ...

    def check(self, sample: str | None = None) -> str: ...


class DiskStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise AppError("invalid", "Invalid file key.", status_code=400)
        return path

    def read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise _missing() from exc
        except OSError as exc:
            raise _unreadable() from exc

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Whole or not at all: a crash never leaves half a file under the key.
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            with contextlib.suppress(OSError):  # a broken folder must not hide why
                temporary.unlink(missing_ok=True)
            raise _unstorable() from exc

    def remove(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise _undeletable() from exc

    def check(self, sample: str | None = None) -> str:
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise AppError("unavailable", f"Cannot create the folder {self.root}.", status_code=503) from exc
        if not os.access(self.root, os.W_OK | os.X_OK):
            raise AppError("unavailable", f"Corpus cannot write to {self.root}.", status_code=503)
        return f"Folder {self.root}"


class _Pool(urllib3.PoolManager):
    """With `connect` (production's s3-tunnel), dials it for every request.
    The Host header (minio sets it), the TLS server name and the certificate
    check stay those of the storage itself."""

    def __init__(self, connect: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        host, _, port = connect.rpartition(":")
        self._dial = (host, int(port)) if connect else None

    def connection_from_host(self, host, port=None, scheme="http", pool_kwargs=None):
        if self._dial is None:
            return super().connection_from_host(host, port, scheme, pool_kwargs)
        extra = dict(pool_kwargs or {})
        if scheme == "https" and host:
            extra |= {"server_hostname": host, "assert_hostname": host}
        return super().connection_from_host(*self._dial, scheme=scheme, pool_kwargs=extra)


def _http_client(config: S3Config) -> urllib3.PoolManager:
    return _Pool(
        config.connect,
        timeout=Timeout(connect=10, read=60),
        maxsize=10,
        cert_reqs="CERT_REQUIRED",
        ca_certs=config.cacert or certifi.where(),
        retries=Retry(total=3, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504]),
    )


class S3Store:
    def __init__(self, config: S3Config, client: Minio | None = None) -> None:
        endpoint = urlsplit(config.endpoint)
        self.where = f"bucket {config.bucket} at {endpoint.netloc}"
        self.bucket = config.bucket
        self.client = client or Minio(
            endpoint.netloc,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=endpoint.scheme == "https",
            region=config.region,
            http_client=_http_client(config),
        )

    def read(self, key: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            raise (_missing() if exc.code in _MISSING_OBJECT else _unreadable()) from exc
        except _TRANSPORT_ERRORS as exc:
            raise _unreadable() from exc

    def write(self, key: str, data: bytes) -> None:
        try:
            # An opaque blob: the real content type would tell the file's kind.
            self.client.put_object(self.bucket, key, io.BytesIO(data), length=len(data))
        except _TRANSPORT_ERRORS as exc:  # S3Error is a MinioException
            raise _unstorable() from exc

    def remove(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except S3Error as exc:
            if exc.code not in _MISSING_OBJECT:
                raise _undeletable() from exc
        except _TRANSPORT_ERRORS as exc:
            raise _undeletable() from exc

    def check(self, sample: str | None = None) -> str:
        """Reads the details of a document's file (`sample`), or before any
        document of a key that never exists. Without s3:ListBucket, which
        Corpus does not need, a missing object answers AccessDenied instead
        of NoSuchKey (Amazon S3): only a real file tells access apart."""
        try:
            self.client.stat_object(self.bucket, sample or _PROBE_KEY)
        except S3Error as exc:
            if sample is not None and exc.code in _MISSING_OBJECT:
                raise AppError(
                    "unavailable", f"A document file is missing from the S3 storage ({self.where}).", 503
                ) from exc
            if sample is not None or exc.code not in _MISSING_OBJECT | {"AccessDenied"}:
                raise AppError(
                    "unavailable", f"The S3 storage refused Corpus: {exc.code} ({self.where}).", status_code=503
                ) from exc
        except _TRANSPORT_ERRORS as exc:
            raise AppError("unavailable", f"Cannot reach the S3 storage ({self.where}).", status_code=503) from exc
        return self.where[0].upper() + self.where[1:]


def file_store() -> FileStore:
    """The store STORAGE names."""
    return S3Store(s3_config()) if storage() == "s3" else DiskStore(storage_dir())


class ObjectStorage:
    def __init__(self, store: FileStore | None = None) -> None:
        self.store = store or file_store()

    def make_key(self) -> str:
        # No filename: listing the folder or the bucket must not reveal document names.
        return f"documents/{uuid.uuid4()}"

    def put(self, key: str, content: bytes) -> None:
        self.store.write(key, encrypt_bytes(content, key))

    def get(self, key: str) -> bytes:
        return decrypt_bytes(self.store.read(key), key)

    def delete(self, key: str) -> None:
        self.store.remove(key)

    def read_sealed(self, key: str) -> bytes:
        """The stored, still encrypted bytes (key rotation)."""
        return self.store.read(key)

    def write_sealed(self, key: str, data: bytes) -> None:
        self.store.write(key, data)

    def check(self, sample: str | None = None) -> str:
        """Where the files are, once the store answers and lets Corpus in;
        AppError with the reason otherwise (System status page). `sample`:
        the key of a stored document, if any."""
        return self.store.check(sample)
