"""Read-only mirror of the models table for compilation tracking.

The MLOps service is not the owner of the table; it only reads and updates
compile_status via gRPC to the registry service.
"""
from datetime import datetime
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from shared.utils.database import Base

class ModelRef(Base):
    """Local ORM mirror class representing database records of models."""
    __tablename__ = "models"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    """Unique UUID primary key mapping the shared models table."""
    source_key: Mapped[str] = mapped_column(Text)
    """MinIO location object key containing raw weight files."""
    compile_status: Mapped[str] = mapped_column(String)
    """Current build workflow execution status indicator."""
    hardware_type: Mapped[str | None] = mapped_column(String, nullable=True)
    """Target compiler hardware target architecture code."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    """Database record creation timestamp."""
