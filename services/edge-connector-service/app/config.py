"""Configuration Settings module for the Edge Connector Service.

Loads settings from the environment variables (via Pydantic BaseSettings)
and provides a cached get_settings function.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Pydantic settings model mapping environment variables for the Edge Connector."""
    
    postgres_dsn: str = "postgresql+asyncpg://aura:aura_dev@localhost:5432/aura"
    """PostgreSQL database DSN string with asyncpg connection parameters."""
    
    minio_endpoint: str = "localhost:9000"
    """MinIO Object Storage service network host and port."""
    
    minio_access_key: str = "aura"
    """Access credential key for MinIO Object Storage connection."""
    
    minio_secret_key: str = "aura_dev"
    """Secret credential key for MinIO Object Storage connection."""
    
    minio_secure: bool = False
    """Specifies if HTTPS should be used instead of HTTP for MinIO connections."""
    
    minio_bucket_compiled: str = "compiled"
    """Bucket containing compiled hardware binaries."""
    
    minio_bucket_scripts: str = "scripts"
    """Bucket containing custom python inference scripts."""
    
    mqtt_host: str = "localhost"
    """MQTT Broker hostname/IP address."""
    
    mqtt_port: int = 1883
    """MQTT Broker network port."""
    
    ai_service_grpc: str = "registry-service:50051"
    """gRPC endpoint for Registry/AI services."""
    
    script_service_grpc: str = "registry-service:50051"
    """gRPC endpoint for Registry/Script services."""
    
    device_service_grpc: str = "registry-service:50051"
    """gRPC endpoint for Registry/Device services."""
    
    compilation_service_grpc: str = "mlops-service:50052"
    """gRPC endpoint for Compilation services."""
    
    download_url_expiry_seconds: int = 3600
    """Duration in seconds before generated presigned download URLs expire."""
    
    grpc_port: int = 50053
    """Port to listen for incoming gRPC connections."""
    
    log_level: str = "DEBUG"
    """Service output logger verbosity (e.g. DEBUG, INFO, WARNING, ERROR)."""
    
    redis_url: str = "redis://localhost:6379"
    """URL protocol string for connecting to the shared Redis instance."""
    
    mongo_uri: str = "mongodb://aura:aura_dev@localhost:27017/aura?authSource=admin"
    """MongoDB connection string DSN."""
    
    mongo_db: str = "aura"
    """Database name in MongoDB to save telemetry."""
    
    prometheus_port: int = 9100
    """Port to expose prometheus client metrics scraper."""

    class Config:
        """Pydantic config for setting dotenv variables path."""
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    """Instantiates and returns the cached configuration singleton.

    Returns:
        The validated Edge Connector settings instance.
    """
    return Settings()
