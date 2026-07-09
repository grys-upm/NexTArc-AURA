"""API Gateway entry point.

FastAPI application that acts as the single HTTP entry point for the
frontend. Authenticates requests with JWT and proxies them to the
appropriate downstream gRPC service. Handles multipart file uploads
directly to MinIO to avoid passing large binaries through gRPC.
"""
import logging, sys
from contextlib import asynccontextmanager
sys.path.insert(0, "/app")

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.jwt import create_token, DEMO_USER
from app.config import get_settings
from app.stubs import init_stubs
from app.routers import devices, models, scripts, deployments, monitoring, datasets
from shared.utils.logging import configure_logging
from shared.utils.minio import init_minio, ensure_buckets

s = get_settings()
configure_logging("api-gateway", s.log_level)

async def bootstrap_base_models() -> None:
    """Synchronizes and populates allowed reference base models in MinIO.

    Scans the MinIO base-models bucket, removes obsolete items, and creates
    empty placeholders for all valid items listed in ALLOWED_BASE_MODELS.
    """
    import logging
    import io
    from shared.utils.minio import get_minio
    from app.config import get_settings
    from app.routers.models import ALLOWED_BASE_MODELS

    logger = logging.getLogger("api-gateway")
    s = get_settings()
    minio = get_minio()
    bucket = s.minio_bucket_base_models

    try:
        try:
            existing_objects = await minio.list_objects(bucket)
        except IndexError:
            existing_objects = []
            
        existing_names = set()
        for obj in existing_objects:
            if obj.object_name not in ALLOWED_BASE_MODELS:
                await minio.remove_object(bucket, obj.object_name)
                logger.info(f"Cleaned up old base model: {obj.object_name}")
            else:
                existing_names.add(obj.object_name)
        
        for base_model in ALLOWED_BASE_MODELS:
            if base_model not in existing_names:
                await minio.put_object(bucket, base_model, io.BytesIO(b""), 0)
                logger.info(f"Bootstrapped base model: {base_model}")
    except Exception as e:
        logger.error(f"Failed to bootstrap base models: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan manager handling startup and shutdown logic.

    Initializes gRPC clients, connects to MinIO Object Storage, verifies
    bucket existences, and bootstraps default system models.
    """
    init_stubs()
    init_minio(
        endpoint=s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_secure,
        buckets={
            "models":   s.minio_bucket_models,
            "compiled": s.minio_bucket_compiled,
            "scripts":  s.minio_bucket_scripts,
            "datasets": s.minio_bucket_datasets,
            "base-models": s.minio_bucket_base_models,
        },
    )
    await ensure_buckets()
    await bootstrap_base_models()
    logging.getLogger("api-gateway").info("API Gateway ready")
    yield

app = FastAPI(title="AURA Platform API", version="0.1.0", lifespan=lifespan)
"""FastAPI instance serving the core web platform REST routes."""

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/auth/token")
async def login(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    """Authenticates the incoming username and password for a JWT access token.

    Args:
        form: OAuth2 form fields carrying username and password.

    Returns:
        JSON response with the generated JWT access token.

    Raises:
        HTTPException: If user validation fails (status 401).
    """
    if form.username != DEMO_USER["username"] or form.password != DEMO_USER["password"]:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": create_token(form.username), "token_type": "bearer"}

@app.get("/health")
async def health() -> dict:
    """Verifies that the API Gateway is running and healthy.

    Returns:
        Dictionary status descriptor object.
    """
    return {"status": "ok", "platform": "AURA"}

app.include_router(devices.router)
app.include_router(models.router)
app.include_router(datasets.router)
app.include_router(scripts.router)
app.include_router(deployments.router)
app.include_router(monitoring.router)

