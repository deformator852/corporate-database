import io
import uuid
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from exceptions import AppError
from settings import (
    minio_access_key,
    minio_bucket,
    minio_endpoint,
    minio_secret_key,
    minio_secure,
)

_MISSING_OBJECT = frozenset({"NoSuchKey", "NoSuchObject", "NoSuchBucket"})


class ObjectStorage:
    def __init__(self, client: Minio | None = None, bucket: str | None = None) -> None:
        self.client = client or Minio(
            minio_endpoint(),
            access_key=minio_access_key(),
            secret_key=minio_secret_key(),
            secure=minio_secure(),
        )
        self.bucket = bucket or minio_bucket()

    def ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as exc:
            raise AppError(
                "unavailable",
                "Could not reach object storage.",
                status_code=503,
            ) from exc

    def make_key(self, filename: str) -> str:
        return f"documents/{uuid.uuid4()}/{Path(filename).name}"

    def put(self, *, key: str, content: bytes, content_type: str) -> None:
        self.ensure_bucket()
        try:
            self.client.put_object(
                self.bucket,
                key,
                io.BytesIO(content),
                length=len(content),
                content_type=content_type,
            )
        except S3Error as exc:
            raise AppError(
                "unavailable",
                "Could not store the document.",
                status_code=503,
            ) from exc

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            if exc.code in _MISSING_OBJECT:
                raise AppError(
                    "not_found",
                    "The document file is missing.",
                    status_code=503,
                ) from exc
            raise AppError(
                "unavailable",
                "Could not read the document.",
                status_code=503,
            ) from exc

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except S3Error as exc:
            if exc.code in _MISSING_OBJECT:
                return
            raise AppError(
                "unavailable",
                "Could not delete the document file.",
                status_code=503,
            ) from exc
