"""
MinIO / S3 Object Storage Adapter.
"""

import io
import logging
from typing import BinaryIO, Optional
from minio import Minio
from minio.error import S3Error

from backend.app.core.config import settings

logger = logging.getLogger("mahavistaar.storage")
from backend.app.ports.storage_port import StoragePort


class MinioStorageAdapter(StoragePort):
    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        secure: Optional[bool] = None,
    ):
        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.bucket_name = bucket_name or settings.MINIO_BUCKET
        self.secure = secure if secure is not None else settings.MINIO_SECURE

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )
        self._ensure_bucket()

    def _describe(self, exc: Exception) -> str:
        """Storage failures are almost always the server being down or the
        credentials being wrong, and the raw urllib3 traceback says neither."""
        text = str(exc)
        if "Connection refused" in text or "Max retries exceeded" in text:
            return (f"MinIO is not reachable at {self.endpoint}. Start it, or correct "
                    f"MINIO_ENDPOINT in the root .env.")
        if "AccessDenied" in text or "SignatureDoesNotMatch" in text or "InvalidAccessKeyId" in text:
            return (f"MinIO at {self.endpoint} rejected the credentials. Check "
                    f"MINIO_ACCESS_KEY and MINIO_SECRET_KEY.")
        if "NoSuchBucket" in text:
            return f"Bucket '{self.bucket_name}' does not exist on {self.endpoint}."
        return f"MinIO error against {self.endpoint}/{self.bucket_name}: {text}"

    def _ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info("created bucket '%s' on %s", self.bucket_name, self.endpoint)
        except Exception as exc:
            # This used to swallow every failure silently, so an unreachable
            # server only surfaced later as a traceback from deep inside urllib3.
            logger.warning("bucket check failed | %s", self._describe(exc))

    def upload_file(
        self,
        object_name: str,
        file_data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=file_data,
                length=length,
                content_type=content_type,
            )
        except Exception as exc:
            message = self._describe(exc)
            logger.error("upload failed | object=%s bytes=%d | %s", object_name, length, message)
            raise RuntimeError(message) from exc
        logger.info("stored | object=%s bytes=%d type=%s", object_name, length, content_type)
        return f"minio://{self.bucket_name}/{object_name}"

    def download_file(self, object_name: str, target_path: str) -> str:
        self.client.fget_object(self.bucket_name, object_name, target_path)
        return target_path

    def get_object_bytes(self, object_name: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket_name, object_name)
        except Exception as exc:
            message = self._describe(exc)
            logger.error("read failed | object=%s | %s", object_name, message)
            raise RuntimeError(message) from exc
        try:
            data = response.read()
            logger.debug("read | object=%s bytes=%d", object_name, len(data))
            return data
        finally:
            response.close()
            response.release_conn()

    def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        from datetime import timedelta
        return self.client.presigned_get_object(
            self.bucket_name, object_name, expires=timedelta(seconds=expires_seconds)
        )

    def delete_object(self, object_name: str) -> bool:
        try:
            self.client.remove_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False
