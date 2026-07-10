"""
backend/src/core/storage.py

MinIO S3-compatible object storage client.
All credentials are sourced from the secrets abstraction (constitution §V).
"""
from __future__ import annotations

import io
import logging
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from src.core.secrets import require_secret, get_secret

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    """Return the process-level MinIO client (lazy singleton)."""
    endpoint = require_secret("MINIO_ENDPOINT")
    access_key = require_secret("MINIO_ACCESS_KEY")
    secret_key = require_secret("MINIO_SECRET_KEY")
    secure = (get_secret("MINIO_SECURE") or "false").lower() == "true"

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    logger.info("MinIO client initialized: endpoint=%s secure=%s", endpoint, secure)
    return client


def get_bucket_name() -> str:
    return get_secret("MINIO_BUCKET") or "pa-case-documents"


def upload_document(
    object_key: str,
    data: bytes,
    content_type: str = "application/pdf",
) -> str:
    """
    Upload *data* to MinIO under *object_key*.
    Returns the object_key (used as Document.storage_path).

    Raises S3Error on failure.
    """
    client = get_minio_client()
    bucket = get_bucket_name()

    client.put_object(
        bucket_name=bucket,
        object_name=object_key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    logger.info("Uploaded document: bucket=%s key=%s size=%d", bucket, object_key, len(data))
    return object_key


def get_document_url(object_key: str, expires_seconds: int = 3600) -> str:
    """Return a pre-signed GET URL for the given object_key."""
    from datetime import timedelta

    client = get_minio_client()
    bucket = get_bucket_name()
    url = client.presigned_get_object(
        bucket_name=bucket,
        object_name=object_key,
        expires=timedelta(seconds=expires_seconds),
    )
    return url
