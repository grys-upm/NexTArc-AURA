"""REST API Router for managing datasets.

Supports uploading dataset ZIP archives, executing file structure integrity checks,
managing dataset versions, and retrieving presigned download links.
"""
import io
import json
import uuid
import zipfile
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth.jwt import verify_token
from app.stubs import get_stub
from shared.proto_gen import ai_pb2
from shared.utils.minio import upload_bytes, presigned_url

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
"""APIRouter instance for dataset endpoints."""

def validate_dataset_zip(file_bytes: bytes) -> tuple[bool, str, int, list[str]]:
    """Validates that a dataset ZIP archive follows the YOLO format structure.

    Checks for the existence of `classes.json`, an `images/` directory, and
    a `labels/` directory, and extracts the list of class names.

    Args:
        file_bytes: Raw binary content of the ZIP archive.

    Returns:
        A tuple of (is_valid, error_message, num_classes, list_of_class_names).
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            namelist = z.namelist()
            classes_paths = [p for p in namelist if p.endswith("classes.json")]
            if not classes_paths:
                return False, "Missing 'classes.json' in the zip file.", 0, []

            classes_path = classes_paths[0]
            base_dir = classes_path[:-len("classes.json")]

            images_prefix = f"{base_dir}images/"
            labels_prefix = f"{base_dir}labels/"

            has_images = any(p.startswith(images_prefix) and p != images_prefix for p in namelist)
            has_labels = any(p.startswith(labels_prefix) and p != labels_prefix for p in namelist)

            if not has_images:
                return False, f"Missing 'images/' directory or it is empty under '{base_dir}'.", 0, []
            if not has_labels:
                return False, f"Missing 'labels/' directory or it is empty under '{base_dir}'.", 0, []

            try:
                classes_content = z.read(classes_path)
                classes_data = json.loads(classes_content)
                
                if isinstance(classes_data, list):
                    class_names = [str(x) for x in classes_data]
                elif isinstance(classes_data, dict):
                    try:
                        # Format A: {"0": "alert", "1": "drowsy"} (index -> name)
                        first_key = next(iter(classes_data.keys()))
                        int(first_key)
                        sorted_keys = sorted(classes_data.keys(), key=lambda k: int(k))
                        class_names = [str(classes_data[k]) for k in sorted_keys]
                    except (ValueError, TypeError):
                        try:
                            # Format B: {"alert": 0, "drowsy": 1} (name -> index)
                            sorted_keys = sorted(classes_data.keys(), key=lambda k: int(classes_data[k]))
                            class_names = [str(k) for k in sorted_keys]
                        except (ValueError, TypeError):
                            class_names = sorted([str(k) for k in classes_data.keys()])
                else:
                    return False, "'classes.json' must be a JSON list or dictionary.", 0, []
                
                num_classes = len(class_names)
            except Exception as je:
                return False, f"Failed to parse 'classes.json': {je}", 0, []

            return True, "", num_classes, class_names
    except zipfile.BadZipFile:
        return False, "The uploaded file is not a valid zip file.", 0, []
    except Exception as e:
        return False, f"Error validating zip file: {e}", 0, []

@router.post("", status_code=201)
async def create_dataset(
    name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(None),
    version: str = Form(""),
    version_description: str = Form(""),
    _=Depends(verify_token),
) -> dict:
    """Registers a new dataset, uploading its initial version ZIP file if provided.

    Args:
        name: Name of the dataset.
        description: Description of the dataset.
        file: Optional ZIP archive file containing images and labels.
        version: Version tag (e.g. '1.0.0').
        version_description: Version release notes.

    Returns:
        Dictionary representation of the created dataset and its initial version.

    Raises:
        HTTPException: If zip validation fails (status 400).
    """
    file_bytes = None
    num_classes = 0
    class_names = []
    if file:
        file_bytes = await file.read()
        is_valid, err_msg, num_classes, class_names = validate_dataset_zip(file_bytes)
        if not is_valid:
            raise HTTPException(status_code=400, detail=err_msg)

    ai_stub = get_stub("ai")
    d = await ai_stub.UploadDataset(
        ai_pb2.UploadDatasetRequest(name=name, description=description)
    )

    if file and file_bytes:
        object_key = f"{d.id}/{uuid.uuid4()}-{file.filename or 'dataset.zip'}"
        sha = await upload_bytes("datasets", object_key, file_bytes)
        d = await ai_stub.SetDatasetFile(
            ai_pb2.SetDatasetFileRequest(
                dataset_id=d.id,
                object_key=object_key,
                sha256=sha,
                size_bytes=len(file_bytes),
                metadata=json.dumps({"num_classes": num_classes, "class_names": class_names}),
                version=version,
                description=version_description,
            )
        )

    return _dataset_resp(d)

@router.get("")
async def list_datasets(_=Depends(verify_token)) -> list[dict]:
    """Retrieves all registered datasets and their active versions.

    Returns:
        List of datasets.
    """
    r = await get_stub("ai").ListDatasets(ai_pb2.ListDatasetsRequest())
    return [_dataset_resp(d) for d in r.datasets]

@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, _=Depends(verify_token)) -> dict:
    """Retrieves a single dataset's metadata and all historical versions.

    Args:
        dataset_id: Dataset UUID string.

    Returns:
        Dataset details.
    """
    d = await get_stub("ai").GetDataset(ai_pb2.GetDatasetRequest(id=dataset_id))
    return _dataset_resp(d)

@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str, _=Depends(verify_token)) -> None:
    """Deletes a dataset and all associated version references.

    Args:
        dataset_id: Dataset UUID string.
    """
    await get_stub("ai").DeleteDataset(ai_pb2.DeleteDatasetRequest(id=dataset_id))

@router.put("/{dataset_id}/file", status_code=200)
async def replace_dataset_file(
    dataset_id: str,
    file: UploadFile = File(...),
    version: str = Form(""),
    version_description: str = Form(""),
    _=Depends(verify_token),
) -> dict:
    """Uploads a new file version for an existing dataset record.

    Args:
        dataset_id: Target dataset UUID string.
        file: New ZIP archive file.
        version: Version tag.
        version_description: Version release notes.

    Returns:
        Updated dataset details.

    Raises:
        HTTPException: If zip validation fails (status 400).
    """
    data = await file.read()
    is_valid, err_msg, num_classes, class_names = validate_dataset_zip(data)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err_msg)

    object_key = f"{dataset_id}/{uuid.uuid4()}-{file.filename or 'dataset.zip'}"
    sha = await upload_bytes("datasets", object_key, data)

    d = await get_stub("ai").SetDatasetFile(
        ai_pb2.SetDatasetFileRequest(
            dataset_id=dataset_id,
            object_key=object_key,
            sha256=sha,
            size_bytes=len(data),
            metadata=json.dumps({"num_classes": num_classes, "class_names": class_names}),
            version=version,
            description=version_description,
        )
    )
    return _dataset_resp(d)

@router.get("/{dataset_id}/download")
async def download_dataset(dataset_id: str, _=Depends(verify_token)) -> dict:
    """Generates a presigned URL to download the current/latest dataset ZIP file.

    Args:
        dataset_id: Target dataset UUID string.

    Returns:
        JSON object containing the presigned download URL.

    Raises:
        HTTPException: If dataset has no file or file is missing (status 404).
    """
    d = await get_stub("ai").GetDataset(ai_pb2.GetDatasetRequest(id=dataset_id))
    if not d.object_key:
        raise HTTPException(404, "This dataset has no file uploaded yet.")
    try:
        from shared.utils.minio import get_minio
        from app.config import get_settings
        s_cfg = get_settings()
        minio = get_minio()
        await minio.stat_object(s_cfg.minio_bucket_datasets, d.object_key)
    except Exception:
        raise HTTPException(404, "Dataset file not found in storage.")
    url = await presigned_url("datasets", d.object_key)
    return {"url": url}

@router.get("/{dataset_id}/versions/{version_id}/download")
async def download_dataset_version(dataset_id: str, version_id: str, _=Depends(verify_token)) -> dict:
    """Generates a presigned URL to download a specific historical version ZIP.

    Args:
        dataset_id: Target dataset UUID string.
        version_id: Specific version UUID string.

    Returns:
        JSON object containing the presigned download URL.

    Raises:
        HTTPException: If version does not exist or version file is missing (status 404).
    """
    d = await get_stub("ai").GetDataset(ai_pb2.GetDatasetRequest(id=dataset_id))
    version_key = None
    for v in d.versions:
        if v.id == version_id:
            version_key = v.object_key
            break

    if not version_key:
        raise HTTPException(404, "This dataset version does not exist or has no file.")

    try:
        from shared.utils.minio import get_minio
        from app.config import get_settings
        s_cfg = get_settings()
        minio = get_minio()
        await minio.stat_object(s_cfg.minio_bucket_datasets, version_key)
    except Exception:
        raise HTTPException(404, "Dataset version file not found in storage.")
    url = await presigned_url("datasets", version_key)
    return {"url": url}

class UpdateDatasetRequestSchema(BaseModel):
    """Pydantic schema representing dataset metadata update fields."""
    name: str
    """New name for the dataset."""
    description: str = ""
    """New description text."""

@router.put("/{dataset_id}")
async def update_dataset(dataset_id: str, req: UpdateDatasetRequestSchema, _=Depends(verify_token)) -> dict:
    """Updates core catalog information (name/description) of a dataset.

    Args:
        dataset_id: Dataset UUID string.
        req: Updated properties schema.

    Returns:
        Updated dataset details.

    Raises:
        HTTPException: If dataset cannot be found (status 404).
    """
    try:
        d = await get_stub("ai").UpdateDataset(ai_pb2.UpdateDatasetRequest(
            id=dataset_id,
            name=req.name,
            description=req.description,
        ))
        return _dataset_resp(d)
    except Exception as e:
        raise HTTPException(404, f"Dataset not found: {e}")

def _dataset_resp(d) -> dict:
    """Converts a dataset gRPC Protobuf object into a serializable API dict.

    Args:
        d: The dataset gRPC object from the registry service.

    Returns:
        A dictionary representation suited for REST response serialization.
    """
    versions_list = []
    if d.versions:
        for v in d.versions:
            v_meta = None
            if v.metadata:
                try:
                    v_meta = json.loads(v.metadata)
                except Exception:
                    pass
            versions_list.append({
                "id": v.id,
                "dataset_id": v.dataset_id,
                "version": v.version,
                "description": v.description or "",
                "object_key": v.object_key,
                "sha256": v.sha256,
                "size_bytes": v.size_bytes,
                "metadata": v_meta,
                "created_at": v.created_at,
            })
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "created_at": d.created_at,
        "object_key": d.object_key or None,
        "sha256": d.sha256 or None,
        "size_bytes": d.size_bytes or None,
        "metadata": json.loads(d.metadata) if d.metadata else None,
        "versions": versions_list,
    }
