"""Maintenance migration script to parse class names from existing dataset ZIP files.

Downloads the ZIP archives from MinIO, extracts class names from `classes.json`,
and updates metadata fields on DatasetVersion and Dataset tables in PostgreSQL.
"""
import sys
import os
import asyncio
import logging
import tempfile
import zipfile
import json

sys.path.insert(0, "/app")

from app.config import get_settings
from app.models.orm import Dataset, DatasetVersion
from shared.utils.database import build_engine, build_session_factory
from shared.utils.minio import init_minio, get_minio
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_existing_datasets")
"""Logger instance specific to this migration script."""

async def extract_classes_from_zip(bucket: str, object_key: str) -> list[str]:
    """Downloads a dataset ZIP from MinIO and parses labels from its classes.json file.

    Args:
        bucket: Name of the MinIO bucket.
        object_key: Target file object storage key.

    Returns:
        List of parsed class name strings.

    Raises:
        ValueError: If classes.json is missing or carries invalid structure formats.
    """
    minio = get_minio()
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "dataset.zip")
        await minio.fget_object(bucket, object_key, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            classes_file = None
            for name in zip_ref.namelist():
                if name.endswith("classes.json"):
                    classes_file = name
                    break
            if not classes_file:
                raise ValueError("classes.json not found in dataset zip")
            with zip_ref.open(classes_file) as f:
                classes_data = json.load(f)
            
            if isinstance(classes_data, list):
                return [str(x) for x in classes_data]
            elif isinstance(classes_data, dict):
                try:
                    # Format A: {"0": "alert", "1": "drowsy"} (index -> name)
                    first_key = next(iter(classes_data.keys()))
                    int(first_key)
                    sorted_keys = sorted(classes_data.keys(), key=lambda k: int(k))
                    return [str(classes_data[k]) for k in sorted_keys]
                except (ValueError, TypeError):
                    try:
                        # Format B: {"alert": 0, "drowsy": 1} (name -> index)
                        sorted_keys = sorted(classes_data.keys(), key=lambda k: int(classes_data[k]))
                        return [str(k) for k in sorted_keys]
                    except (ValueError, TypeError):
                        return sorted([str(k) for k in classes_data.keys()])
            else:
                raise ValueError("'classes.json' must be a JSON list or dictionary.")

async def main() -> None:
    """Connects to SQL and MinIO databases, lists all dataset versions, and updates metadata."""
    s = get_settings()
    engine = build_engine(s.postgres_dsn)
    sf = build_session_factory(engine)

    init_minio(s.minio_endpoint, s.minio_access_key, s.minio_secret_key, s.minio_secure,
               {
                   "datasets": s.minio_bucket_datasets,
               })

    async with sf() as session:
        r = await session.execute(select(DatasetVersion))
        versions = r.scalars().all()
        logger.info(f"Found {len(versions)} dataset versions to process.")

        for v in versions:
            if not v.object_key:
                continue
            logger.info(f"Processing version {v.version} (dataset ID: {v.dataset_id}) with key {v.object_key}...")
            try:
                classes = await extract_classes_from_zip(s.minio_bucket_datasets, v.object_key)
                logger.info(f"Found classes: {classes}")
                
                # Update DatasetVersion meta_info
                current_meta = v.meta_info or {}
                current_meta["class_names"] = classes
                current_meta["num_classes"] = len(classes)
                v.meta_info = current_meta
                session.add(v)
                
                # Update parent Dataset metadata if it matches this version's object_key
                parent = await session.get(Dataset, v.dataset_id)
                if parent and parent.object_key == v.object_key:
                    parent_meta = parent.meta_info or {}
                    parent_meta["class_names"] = classes
                    parent_meta["num_classes"] = len(classes)
                    parent.meta_info = parent_meta
                    session.add(parent)
                    logger.info(f"Updated parent Dataset {parent.id} metadata.")
                
                await session.commit()
                logger.info(f"Successfully updated version {v.id}.")
            except Exception as e:
                logger.error(f"Failed to process version {v.id}: {e}")

    logger.info("Done updating datasets.")

if __name__ == "__main__":
    asyncio.run(main())
