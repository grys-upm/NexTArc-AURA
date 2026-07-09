"""Configuration Settings module for the MLOps Service.

Loads settings from the environment variables (via Pydantic BaseSettings)
and provides a cached get_settings function.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Pydantic settings model mapping environment variables for the MLOps Service."""
    
    postgres_dsn: str = "postgresql+asyncpg://aura:aura_dev@localhost:5432/aura"
    """PostgreSQL database connection DSN string using asyncpg driver."""
    
    minio_endpoint: str = "localhost:9000"
    """MinIO Object Storage service network endpoint address."""
    
    minio_access_key: str = "aura"
    """Access credential key for MinIO Object Storage connection."""
    
    minio_secret_key: str = "aura_dev"
    """Secret credential key for MinIO Object Storage connection."""
    
    minio_secure: bool = False
    """Specifies if HTTPS should be used instead of HTTP for MinIO connections."""
    
    minio_bucket_models: str = "models"
    """Bucket containing raw model source files."""
    
    minio_bucket_compiled: str = "compiled"
    """Bucket containing compiled hardware binaries."""
    
    ai_service_grpc: str = "registry-service:50051"
    """gRPC endpoint address for the device/registry service."""
    
    grpc_port: int = 50052
    """Port to listen for incoming gRPC connections."""
    
    docker_socket: str = "unix:///var/run/docker.sock"
    """Path to the local Docker daemon socket for launching build containers."""
    
    log_level: str = "DEBUG"
    """Service output logger verbosity (e.g. DEBUG, INFO, WARNING, ERROR)."""
    
    redis_url: str = "redis://localhost:6379"
    """URL protocol string for connecting to the shared Redis instance."""

    class Config:
        """Pydantic config for setting dotenv variables path."""
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    """Instantiates and returns the cached configuration singleton.

    Returns:
        The validated MLOps Service settings instance.
    """
    return Settings()
