"""
Storage Port (Interface for Object Storage / MinIO / S3).
"""

from abc import ABC, abstractmethod
from typing import BinaryIO, Optional


class StoragePort(ABC):
    @abstractmethod
    def upload_file(
        self,
        object_name: str,
        file_data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file stream and return its storage URI (e.g. minio://bucket/path)."""
        pass

    @abstractmethod
    def download_file(self, object_name: str, target_path: str) -> str:
        """Download an object from storage to a local file path."""
        pass

    @abstractmethod
    def get_object_bytes(self, object_name: str) -> bytes:
        """Retrieve raw bytes of an object."""
        pass

    @abstractmethod
    def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        """Generate a temporary pre-signed download URL."""
        pass

    @abstractmethod
    def delete_object(self, object_name: str) -> bool:
        """Delete an object from storage."""
        pass
