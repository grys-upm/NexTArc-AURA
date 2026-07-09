"""SQLAlchemy Object Relational Mapping (ORM) models for the edge connector service.

Defines the database schema mapping for Deployment records and mirror
tables (DeviceRef, ModelRef, ScriptRef) used for database integrity constraints.
"""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from shared.utils.database import Base

def _uuid() -> str:
    """Generates a UUID version 4 string representation.

    Returns:
        UUID string representation.
    """
    return str(uuid.uuid4())

class DeviceRef(Base):
    """Local ORM mirror class representing database records of devices."""
    __tablename__ = "devices"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    """Unique UUID primary key mapping the shared devices table."""
    hardware_type: Mapped[str] = mapped_column(String)
    """Hardware target platform class (e.g. 'rpi', 'hailo8')."""
    status: Mapped[str] = mapped_column(String)
    """Connectivity indicator status."""

class ModelRef(Base):
    """Local ORM mirror class representing database records of models."""
    __tablename__ = "models"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    """Unique UUID primary key mapping the shared models table."""
    source_key: Mapped[str] = mapped_column(Text)
    """MinIO location object key containing raw weight files."""
    compiled_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    """MinIO object key location of compiled model binary."""
    compiled_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    """SHA-256 hash checksum of compiled model binary."""
    hardware_type: Mapped[str | None] = mapped_column(String, nullable=True)
    """Target hardware target architecture code."""
    compile_status: Mapped[str] = mapped_column(String)
    """Current build workflow execution status indicator."""
    dataset_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    """Associated dataset UUID key."""
    dataset_version_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    """Associated dataset version UUID key."""
    base_architecture: Mapped[str | None] = mapped_column(String, nullable=True)
    """Baseline reference weights filename."""
    input_size: Mapped[str | None] = mapped_column(String, nullable=True)
    """Model image input resolution (e.g. '640x640')."""

class ModelCompilationRef(Base):
    """Local ORM mirror class representing compilation target records."""
    __tablename__ = "model_compilations"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    """Unique UUID primary key mapping model compilations."""
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    """Foreign key referencing the parent model database row."""
    hardware_type: Mapped[str] = mapped_column(String, nullable=False)
    """Target compiler hardware type."""
    compiled_key: Mapped[str] = mapped_column(Text, nullable=False)
    """MinIO key containing compiled binary."""
    compiled_sha256: Mapped[str] = mapped_column(String, nullable=False)
    """SHA-256 hash checksum of compiled binary."""
    compile_status: Mapped[str] = mapped_column(String, nullable=False)
    """Compilation execution status."""

class ScriptRef(Base):
    """Local ORM mirror class representing database records of scripts."""
    __tablename__ = "scripts"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    """Unique UUID primary key mapping scripts."""
    language: Mapped[str] = mapped_column(String)
    """Target programming language."""
    script_key: Mapped[str] = mapped_column(Text)
    """MinIO location object key containing script file."""
    script_sha256: Mapped[str] = mapped_column(String)
    """SHA-256 hash checksum of script content."""

class Deployment(Base):
    """Represents an OTA deployment execution mapped to an edge device."""
    __tablename__ = "deployments"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    """Unique UUID primary key."""
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    """Foreign key linking to target device."""
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    """Foreign key linking to compiled model."""
    script_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False)
    """Foreign key linking to python script."""
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Optional user-defined name describing the deployment."""
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    """Deployment progress state ('pending', 'sent', 'running', 'failed', 'compiling')."""
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """UTC timestamp of when deployment packet was dispatched."""
    running_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """UTC timestamp when the device acknowledged script activation."""
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Error stack trace description if execution failed."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Database record insertion timestamp."""
