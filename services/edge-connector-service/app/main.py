"""Edge Connector Service entry point.

Consolidates OTA deployment orchestration, telemetry monitoring,
and Prometheus metrics. Launches gRPC server, Prometheus exporter,
MQTT background listener, and deployment arq worker.
"""
import asyncio
import logging
import sys
from grpc_reflection.v1alpha import reflection
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_client import start_http_server
from arq import Worker

sys.path.insert(0, "/app")

from app.config import get_settings
from app.grpc_handlers.deployment_handler import DeploymentServiceHandler
from app.grpc_handlers.monitoring_handler import MonitoringServiceHandler
from app.mqtt.listener import EdgeConnectorMQTTListener
from app.repositories.monitoring import MonitoringRepository
from app.models.orm import Base
from app.worker import WorkerSettings

import grpc
from shared.proto_gen import deployment_pb2_grpc, monitoring_pb2_grpc
from shared.utils.database import build_engine, build_session_factory
from shared.utils.grpc_server import serve
from shared.utils.logging import configure_logging
from shared.utils.minio import init_minio, ensure_buckets

async def main() -> None:
    """Bootstraps databases, initializes client wrappers, and runs gRPC, MQTT and ARQ worker."""
    s = get_settings()
    configure_logging("edge-connector-service", s.log_level)
    logger = logging.getLogger("edge-connector-service")

    # 1. PostgreSQL setup (for deployments)
    engine = build_engine(s.postgres_dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = build_session_factory(engine)

    # 2. MongoDB setup (for telemetry & inference)
    mongo = AsyncIOMotorClient(s.mongo_uri)
    db = mongo[s.mongo_db]
    def mongo_repo_factory(): return MonitoringRepository(db)

    # 3. MinIO setup
    init_minio(s.minio_endpoint, s.minio_access_key, s.minio_secret_key, s.minio_secure,
               {"compiled": s.minio_bucket_compiled, "scripts": s.minio_bucket_scripts})
    await ensure_buckets()

    # 4. Prometheus metrics setup
    start_http_server(s.prometheus_port)
    logger.info(f"Prometheus HTTP metrics exporter started on port :{s.prometheus_port}")

    # 5. Unified MQTT Listener
    listener = EdgeConnectorMQTTListener(s.mqtt_host, s.mqtt_port, sf, mongo_repo_factory)
    asyncio.create_task(listener.start())

    # 6. Instantiate handlers
    deployment_handler = DeploymentServiceHandler(
        sf, s.mqtt_host, s.mqtt_port, s.ai_service_grpc, s.compilation_service_grpc, s.redis_url)
    monitoring_handler = MonitoringServiceHandler(mongo_repo_factory)

    # 7. Dual gRPC server and ARQ worker execution
    grpc_server = grpc.aio.server()
    deployment_pb2_grpc.add_DeploymentServiceServicer_to_server(deployment_handler, grpc_server)
    monitoring_pb2_grpc.add_MonitoringServiceServicer_to_server(monitoring_handler, grpc_server)

    service_names = [
        "aura.deployment.v1.DeploymentService",
        "aura.monitoring.v1.MonitoringService",
    ]
    reflection.enable_server_reflection(
        service_names + [reflection.SERVICE_NAME], grpc_server
    )
    grpc_server.add_insecure_port(f"[::]:{s.grpc_port}")
    await grpc_server.start()
    logger.info(f"Edge Connector gRPC server listening on :{s.grpc_port}")

    # Start ARQ worker for deployment tasks
    arq_worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        queue_name=WorkerSettings.queue_name,
        max_jobs=WorkerSettings.max_jobs,
        job_timeout=WorkerSettings.job_timeout,
        keep_result=WorkerSettings.keep_result,
        on_startup=WorkerSettings.on_startup,
        on_shutdown=WorkerSettings.on_shutdown
    )

    try:
        await asyncio.gather(
            grpc_server.wait_for_termination(),
            arq_worker.async_run()
        )
    finally:
        await grpc_server.stop(5)

if __name__ == "__main__":
    asyncio.run(main())
