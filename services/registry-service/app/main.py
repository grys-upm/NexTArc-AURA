"""Registry Service entry point.

Consolidates Device, AI, and Script metadata management.
Starts a single async gRPC server on port 50051 that hosts
DeviceServiceHandler, AIServiceHandler, and ScriptServiceHandler.
"""
import asyncio
import logging
import sys
from grpc_reflection.v1alpha import reflection

sys.path.insert(0, "/app")

from app.config import get_settings
from app.grpc_handlers.device_handler import DeviceServiceHandler
from app.grpc_handlers.ai_handler import AIServiceHandler
from app.grpc_handlers.script_handler import ScriptServiceHandler
from app.models.orm import Base

import grpc
from shared.proto_gen import device_pb2_grpc, ai_pb2_grpc, script_pb2_grpc
from shared.utils.database import build_engine, build_session_factory
from shared.utils.logging import configure_logging
from shared.utils.minio import init_minio, ensure_buckets

async def main() -> None:
    """Bootstraps databases, sets up MinIO storage connection, and runs gRPC server.

    Creates SQL tables and adds migration column constraints, validates object
    storage buckets, hooks service handlers to gRPC server and enables reflection.
    """
    s = get_settings()
    configure_logging("registry-service", s.log_level)
    logger = logging.getLogger("registry-service")
    
    # 1. PostgreSQL setup
    engine = build_engine(s.postgres_dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        # Safeguards for dynamically added columns in older dev databases
        await conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS sensors TEXT[] NOT NULL DEFAULT '{}';"))
        await conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS actuators TEXT[] NOT NULL DEFAULT '{}';"))
        await conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS others TEXT[] NOT NULL DEFAULT '{}';"))
        await conn.execute(text("ALTER TABLE models ADD COLUMN IF NOT EXISTS dataset_version_id UUID REFERENCES dataset_versions(id) ON DELETE SET NULL;"))
    
    sf = build_session_factory(engine)

    # 2. MinIO setup
    init_minio(s.minio_endpoint, s.minio_access_key, s.minio_secret_key, s.minio_secure,
               {
                   "models": s.minio_bucket_models,
                   "compiled": s.minio_bucket_compiled,
                   "datasets": s.minio_bucket_datasets,
                   "base-models": s.minio_bucket_base_models,
                   "scripts": s.minio_bucket_scripts,
               })
    await ensure_buckets()

    # 3. Combined gRPC server
    server = grpc.aio.server()
    device_pb2_grpc.add_DeviceServiceServicer_to_server(DeviceServiceHandler(sf), server)
    ai_pb2_grpc.add_AIServiceServicer_to_server(AIServiceHandler(sf), server)
    script_pb2_grpc.add_ScriptServiceServicer_to_server(ScriptServiceHandler(sf), server)

    service_names = [
        "aura.device.v1.DeviceService",
        "aura.ai.v1.AIService",
        "aura.script.v1.ScriptService",
    ]
    
    reflection.enable_server_reflection(
        service_names + [reflection.SERVICE_NAME], server
    )
    
    server.add_insecure_port(f"[::]:{s.grpc_port}")
    await server.start()
    logger.info(f"Registry Service gRPC server listening on :{s.grpc_port}")
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(main())
