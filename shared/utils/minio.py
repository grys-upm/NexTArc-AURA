"""
MinIO async client helpers for AURA services.
=============================================
Wraps miniopy-async to provide initialisation, bucket bootstrapping,
binary upload and presigned URL generation as simple module-level calls
shared across all services.
"""
from __future__ import annotations

import hashlib
import io
from datetime import timedelta
from typing import Any

import miniopy_async as minio_lib

_client: minio_lib.Minio | None = None
_bucket_map: dict[str, str] = {}
_access_key: str | None = None
_secret_key: str | None = None


def init_minio(
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool,
    buckets: dict[str, str],
) -> None:
    """
    Initialises the global MinIO client and registers logical bucket names.

    Must be called once during application startup before any other
    function in this module is used.

    :param endpoint: MinIO host and port, e.g. "minio:9000".
    :type endpoint: str
    :param access_key: MinIO root / access key.
    :type access_key: str
    :param secret_key: MinIO root / secret key.
    :type secret_key: str
    :param secure: Whether to use TLS (False for local development).
    :type secure: bool
    :param buckets: Mapping from logical bucket key to actual bucket name.
    :type buckets: dict
    """
    global _client, _bucket_map, _access_key, _secret_key
    _access_key = access_key
    _secret_key = secret_key
    _client = minio_lib.Minio(
        endpoint, access_key=access_key, secret_key=secret_key, secure=secure
    )
    _bucket_map = buckets


def get_minio() -> minio_lib.Minio:
    """
    Returns the initialized MinIO client instance.

    :return: The Minio client.
    :rtype: Minio
    :raises RuntimeError: If init_minio has not been called yet.
    """
    if _client is None:
        raise RuntimeError("MinIO not initialized. Call init_minio() first.")
    return _client


async def ensure_buckets() -> None:
    """
    Creates all registered buckets if they do not already exist.
    """
    if _client is None:
        raise RuntimeError("MinIO not initialized. Call init_minio() first.")
    for bucket in _bucket_map.values():
        if not await _client.bucket_exists(bucket):
            await _client.make_bucket(bucket)


async def upload_bytes(bucket_key: str, object_key: str, data: bytes) -> str:
    """
    Uploads raw bytes to MinIO and returns the SHA-256 hex digest.

    :param bucket_key: Logical bucket key as registered in init_minio.
    :type bucket_key: str
    :param object_key: Object path inside the bucket, e.g. "{model_id}/source.pt".
    :type object_key: str
    :param data: Raw bytes to upload.
    :type data: bytes
    :return: Hex-encoded SHA-256 digest of data.
    :rtype: str
    """
    if _client is None:
        raise RuntimeError("MinIO not initialized. Call init_minio() first.")
    bucket = _bucket_map[bucket_key]
    sha = hashlib.sha256(data).hexdigest()
    await _client.put_object(bucket, object_key, io.BytesIO(data), len(data))
    return sha


async def presigned_url(
    bucket_key: str,
    object_key: str,
    expiry_seconds: int = 3600,
) -> str:
    """
    Generates a presigned GET URL for a MinIO object.

    :param bucket_key: Logical bucket key.
    :type bucket_key: str
    :param object_key: Object path inside the bucket.
    :type object_key: str
    :param expiry_seconds: URL validity in seconds. Defaults to 3600 (1 hour).
    :type expiry_seconds: int
    :return: A presigned HTTPS/HTTP URL string valid for expiry_seconds.
    :rtype: str
    """
    import os
    from urllib.parse import urlparse
    
    if _client is None:
        raise RuntimeError("MinIO not initialized. Call init_minio() first.")
        
    bucket = _bucket_map[bucket_key]
    public_url = os.getenv("MINIO_PUBLIC_URL")
    if public_url:
        parsed_public = urlparse(public_url)
        host = parsed_public.netloc
        scheme = parsed_public.scheme
        
        tmp_client = minio_lib.Minio(
            host, 
            access_key=_access_key, 
            secret_key=_secret_key, 
            secure=(scheme == "https"),
            region="us-east-1"
        )
        url = await tmp_client.presigned_get_object(
            bucket, object_key, expires=timedelta(seconds=expiry_seconds)
        )
    else:
        url = await _client.presigned_get_object(
            bucket, object_key, expires=timedelta(seconds=expiry_seconds)
        )
        
    return url
