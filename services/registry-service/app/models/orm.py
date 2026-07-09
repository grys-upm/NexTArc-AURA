"""SQLAlchemy Object Relational Mapping (ORM) models for the registry service.

Defines the database schema mapping for devices, datasets, dataset versions,
models, model compilations, and script records in PostgreSQL.
"""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func, BigInteger, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.utils.database import Base

def _uuid() -> str:
    """Generates a UUID version 4 string representation.

    Returns:
        UUID string representation.
    """
    return str(uuid.uuid4())

class Device(Base):
    """Represents a registered edge device and its active capabilities."""
    __tablename__ = "devices"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    """Unique UUID primary key."""
    name: Mapped[str] = mapped_column(String, nullable=False)
    """Human-readable display name of the device."""
    hardware_type: Mapped[str] = mapped_column(String, nullable=False)
    """Hardware target platform class (e.g. 'rpi', 'hailo8')."""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Detailed comments or info."""
    status: Mapped[str] = mapped_column(String, nullable=False, default="offline")
    """Connectivity indicator ('online', 'offline', etc.)."""
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """UTC timestamp of the last heart-beat message received."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Database record insertion timestamp."""
    sensors: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default='{}')
    """String array containing names of enabled sensor modules."""
    actuators: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default='{}')
    """String array containing names of enabled actuator modules."""
    others: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default='{}')
    """String array containing names of other peripheral modules."""

class Dataset(Base):
    """Represents an uploaded dataset catalog folder containing versions."""
    __tablename__ = "datasets"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    """Unique UUID primary key."""
    name: Mapped[str] = mapped_column(String, nullable=False)
    """Human-readable display name of the dataset."""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Brief dataset summary info."""
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    """MinIO object path to the current/active zip archive."""
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    """SHA-256 integrity checksum for the current zip file."""
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    """File size of the current zip archive in bytes."""
    meta_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """JSON dictionary specifying metrics (number of classes, labels list)."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Database record insertion timestamp."""

    models: Mapped[list["Model"]] = relationship(back_populates="dataset")
    """Associated ML models referencing this dataset."""
    versions: Mapped[list["DatasetVersion"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetVersion.created_at.desc()"
    )
    """List of uploaded versions for this dataset."""

class DatasetVersion(Base):
    """Tracks historical uploads and files associated with a dataset."""
    __tablename__ = "dataset_versions"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    """Unique UUID primary key."""
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    """Foreign key linking to parent dataset."""
    version: Mapped[str] = mapped_column(String, nullable=False)
    """User-defined version tag string (e.g. '1.0.0')."""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Optional release notes."""
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    """MinIO object key storage location for this version."""
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    """SHA-256 checksum verification tag."""
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    """Size in bytes of this archive version."""
    meta_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Parsed JSON classes info dictionary."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Database record creation timestamp."""

    dataset: Mapped["Dataset"] = relationship(back_populates="versions")
    """Parent dataset relationship object."""

class Model(Base):
    """Represents a machine learning model registry record."""
    __tablename__ = "models"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    """Unique UUID primary key."""
    name: Mapped[str] = mapped_column(String, nullable=False)
    """Human readable name for the model."""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Optional text description."""
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    """MinIO object storage path to the raw input weights."""
    source_sha256: Mapped[str] = mapped_column(String, nullable=False)
    """SHA-256 hash checksum of the source model weights."""
    compiled_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    """MinIO object storage path to the compiled output binary."""
    compiled_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    """SHA-256 checksum of the compiled model binary."""
    hardware_type: Mapped[str | None] = mapped_column(String, nullable=True)
    """Target compiler hardware device architecture type."""
    compile_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    """Current build workflow execution status ('pending', 'compiling', 'ready', 'failed')."""
    compile_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Error stack trace description if compilation step fails."""
    dataset_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    """Associated dataset foreign key."""
    dataset_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    """Associated dataset version foreign key."""
    base_architecture: Mapped[str | None] = mapped_column(String, nullable=True)
    """Parent baseline weights architecture config."""
    epochs: Mapped[int | None] = mapped_column(nullable=True)
    """Metadata training count parameter."""
    input_size: Mapped[str | None] = mapped_column(String, nullable=True)
    """Input resolution model parameters (e.g. '640x640')."""
    batch_size: Mapped[int | None] = mapped_column(nullable=True)
    """Training batch size parameter."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Database record insertion timestamp."""

    dataset: Mapped["Dataset | None"] = relationship(back_populates="models")
    """Associated dataset relationship."""
    compilations: Mapped[list["ModelCompilation"]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="ModelCompilation.created_at.desc()"
    )
    """Available compiled targets list."""

class ModelCompilation(Base):
    """Tracks individual compilation target runs for a parent model."""
    __tablename__ = "model_compilations"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    """Unique UUID primary key."""
    model_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    """Foreign key referencing the parent model database row."""
    hardware_type: Mapped[str] = mapped_column(String, nullable=False)
    """Target compiler hardware type."""
    compiled_key: Mapped[str] = mapped_column(Text, nullable=False)
    """MinIO object key storage location for the compiled output binary."""
    compiled_sha256: Mapped[str] = mapped_column(String, nullable=False)
    """SHA-256 checksum for the compiled output binary."""
    compile_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    """Compilation status."""
    compile_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Compilation error if failed."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Creation timestamp."""

    model: Mapped["Model"] = relationship(back_populates="compilations")
    """Parent model relationship."""

class Script(Base):
    """Represents a user inference Python script record."""
    __tablename__ = "scripts"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    """Unique UUID primary key."""
    name: Mapped[str] = mapped_column(String, nullable=False)
    """Label description name for the script."""
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Brief comments about the script details."""
    language: Mapped[str] = mapped_column(String, nullable=False)
    """Language name of the script ('python')."""
    script_key: Mapped[str] = mapped_column(Text, nullable=False)
    """MinIO object key path containing the script file."""
    script_sha256: Mapped[str] = mapped_column(String, nullable=False)
    """SHA-256 hash checksum of the script contents."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Database insertion timestamp."""
