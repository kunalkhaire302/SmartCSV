"""
Storage Backend Abstraction – LocalStorage and S3Storage.

Provides a unified interface for file persistence. Backend is selected
via the ``STORAGE_BACKEND`` environment variable ("local" or "s3").

Usage::

    from utils.storage import get_storage
    storage = get_storage()
    storage.save("uploads/myfile.csv", raw_bytes)
    data = storage.load("uploads/myfile.csv")
"""

from __future__ import annotations

import io
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

import config
from utils.logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Abstract base
# ═══════════════════════════════════════════════════════════════════════

class StorageBackend(ABC):
    """Abstract interface every storage backend must implement."""

    @abstractmethod
    def save(self, key: str, data: bytes) -> str:
        """Store raw bytes under *key* and return the key."""

    @abstractmethod
    def load(self, key: str) -> bytes:
        """Return raw bytes for *key*."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return ``True`` if *key* exists."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete *key*. No-op if it does not exist."""

    @abstractmethod
    def get_download_path(self, key: str) -> Union[Path, str]:
        """Return a local ``Path`` or a presigned URL for download."""


# ═══════════════════════════════════════════════════════════════════════
#  Local filesystem backend (default)
# ═══════════════════════════════════════════════════════════════════════

class LocalStorage(StorageBackend):
    """Store files on the local filesystem.

    Keys are relative sub-paths, e.g. ``uploads/myfile.csv``.
    The root directory is determined by :pydata:`config.ROOT_STORAGE`.
    """

    def __init__(self) -> None:
        self._root: Path = config.ROOT_STORAGE
        logger.info("LocalStorage initialised (root=%s)", self._root)

    def _resolve(self, key: str) -> Path:
        full = self._root / key
        full.parent.mkdir(parents=True, exist_ok=True)
        return full

    def save(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.write_bytes(data)
        logger.info("LocalStorage: saved %s (%d bytes)", key, len(data))
        return key

    def load(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()
            logger.info("LocalStorage: deleted %s", key)

    def get_download_path(self, key: str) -> Path:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        return path


# ═══════════════════════════════════════════════════════════════════════
#  S3-compatible backend (AWS S3, Cloudflare R2, MinIO)
# ═══════════════════════════════════════════════════════════════════════

class S3Storage(StorageBackend):
    """Store files in an S3-compatible bucket.

    Requires ``boto3`` at runtime. Configuration is read from
    :pymod:`config` (``AWS_*`` vars).  Set ``AWS_S3_ENDPOINT_URL`` for
    Cloudflare R2 or self-hosted MinIO.
    """

    def __init__(self) -> None:
        try:
            import boto3  # lazy import so local dev doesn't need boto3
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3 storage. "
                "Install it with: pip install boto3"
            ) from exc

        self._bucket: str = config.AWS_S3_BUCKET
        if not self._bucket:
            raise ValueError("AWS_S3_BUCKET environment variable is required for S3 storage.")

        client_kwargs: dict = {
            "aws_access_key_id": config.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": config.AWS_SECRET_ACCESS_KEY,
            "region_name": config.AWS_S3_REGION if config.AWS_S3_REGION != "auto" else None,
        }
        if config.AWS_S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = config.AWS_S3_ENDPOINT_URL

        self._client = boto3.client("s3", **client_kwargs)
        logger.info("S3Storage initialised (bucket=%s)", self._bucket)

    def save(self, key: str, data: bytes) -> str:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType="text/csv",
        )
        logger.info("S3Storage: saved %s (%d bytes)", key, len(data))
        return key

    def load(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except self._client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Key not found in S3: {key}")

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
        logger.info("S3Storage: deleted %s", key)

    def get_download_path(self, key: str) -> str:
        """Return a presigned URL valid for 1 hour."""
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=3600,
        )
        return url


# ═══════════════════════════════════════════════════════════════════════
#  Factory / singleton
# ═══════════════════════════════════════════════════════════════════════

_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the configured storage backend (singleton).

    Reads ``config.STORAGE_BACKEND``:
    - ``"local"``  → :class:`LocalStorage`
    - ``"s3"``     → :class:`S3Storage`

    Returns:
        The storage backend instance.
    """
    global _instance
    if _instance is not None:
        return _instance

    backend = config.STORAGE_BACKEND.lower()
    if backend == "s3":
        _instance = S3Storage()
    else:
        _instance = LocalStorage()

    return _instance
