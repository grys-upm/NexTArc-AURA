"""Configuration Settings module for the API Gateway.

Loads settings from the environment variables (via Pydantic BaseSettings)
and provides a cached get_settings function.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Pydantic settings model mapping environment variables for the API Gateway."""
    
    secret_key: str = "dev-insecure-change-me"
    """Secret key used for signing and verifying JWT tokens."""
    
    access_token_expire_minutes: int = 60
    """Duration in minutes before a generated JWT access token expires."""
    
    # gRPC upstreams
    device_service_grpc: str = "device-service:50051"
    """gRPC endpoint address for the device/registry service."""
    
    ai_service_grpc: str = "ai-service:50052"
    """gRPC endpoint address for the AI/model registry service."""
    
    script_service_grpc: str = "script-service:50053"
    """gRPC endpoint address for the script service."""
    
    compilation_service_grpc: str = "mlops-service:50052"
    """gRPC endpoint address for the MLOps compilation service."""
    
    deployment_service_grpc: str = "edge-connector-service:50053"
    """gRPC endpoint address for the edge connector deployment service."""
    
    monitoring_service_grpc: str = "edge-connector-service:50053"
    """gRPC endpoint address for the edge connector monitoring service."""
    
    # MinIO
    minio_endpoint: str = "minio:9000"
    """MinIO Object Storage service network host and port."""
    
    minio_access_key: str = "aura"
    """Access credential key for MinIO Object Storage connection."""
    
    minio_secret_key: str = "aura_dev"
    """Secret credential key for MinIO Object Storage connection."""
    
    minio_secure: bool = False
    """Specifies if HTTPS should be used instead of HTTP for MinIO connections."""
    
    minio_bucket_models: str = "models"
    """Bucket name containing uploaded training/raw ML models."""
    
    minio_bucket_compiled: str = "compiled"
    """Bucket name containing compiled hardware-specific model binaries."""
    
    minio_bucket_scripts: str = "scripts"
    """Bucket name containing user-provided custom inference python scripts."""
    
    minio_bucket_datasets: str = "datasets"
    """Bucket name containing dataset files."""
    
    minio_bucket_base_models: str = "base-models"
    """Bucket name containing base reference models."""
    
    log_level: str = "DEBUG"
    """Server output logger verbosity (e.g. DEBUG, INFO, WARNING, ERROR)."""
    
    redis_url: str = "redis://localhost:6379"
    """URL protocol string for connecting to the shared Redis instance."""

    class Config:
        """Pydantic config for setting dotenv variables path."""
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    """Instantiates and returns the cached configuration singleton.

    Returns:
        The validated API Gateway settings instance.
    """
    return Settings()

