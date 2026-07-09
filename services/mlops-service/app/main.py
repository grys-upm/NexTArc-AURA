"""Compilation Service entry point.

Starts an async gRPC server on port 50052 that exposes
the CompilationServiceHandler and simultaneously runs the ARQ task worker.
"""
import asyncio
import sys
sys.path.insert(0, "/app")
from app.config import get_settings
from app.grpc_handlers.compilation_handler import CompilationServiceHandler
from app.worker import WorkerSettings
from shared.proto_gen import compilation_pb2_grpc
from shared.utils.grpc_server import serve
from shared.utils.logging import configure_logging
from arq import Worker

async def main() -> None:
    """Configures logs, initializes handler registries, and runs gRPC + ARQ workers."""
    s = get_settings()
    configure_logging("mlops-service", s.log_level)

    handler = CompilationServiceHandler(
        s.ai_service_grpc, s.minio_bucket_models, s.minio_bucket_compiled, s.redis_url)

    await asyncio.gather(
        serve(
            port=s.grpc_port,
            add_servicer_fn=compilation_pb2_grpc.add_CompilationServiceServicer_to_server,
            servicer_instance=handler,
            service_names=["aura.compilation.v1.CompilationService"],
        ),
        Worker(functions=WorkerSettings.functions,
               redis_settings=WorkerSettings.redis_settings,
               queue_name=WorkerSettings.queue_name,
               max_jobs=WorkerSettings.max_jobs,
               job_timeout=WorkerSettings.job_timeout,
               keep_result=WorkerSettings.keep_result,
               on_startup=WorkerSettings.on_startup,
               on_shutdown=WorkerSettings.on_shutdown).async_run(),
    )

if __name__ == "__main__":
    asyncio.run(main())
