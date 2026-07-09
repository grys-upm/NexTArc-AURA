"""ARQ task runner and queue background job executors for the Edge Connector Service.

Defines the compile-and-deploy task that coordinates target compile requests and OTA
MQTT deployments, handles database sessions, and handles worker lifespans.
"""
import os
import logging
import asyncio
import json
import aiomqtt
import grpc
import redis.asyncio as aioredis
from arq.connections import RedisSettings

from app.models.orm import Deployment, ModelRef
from app.repositories.deployments import DeploymentRepository
from shared.proto_gen import ai_pb2, ai_pb2_grpc, compilation_pb2, compilation_pb2_grpc
from shared.utils.minio import presigned_url
from app.config import get_settings

logger = logging.getLogger(__name__)
"""Logger instance specific to background worker processes."""


async def compile_and_deploy_job(
    ctx: dict,
    *,
    dep_id: str,
    model_id: str,
    device_id: str,
    script_id: str,
    hardware_type: str,
    source_key: str,
    dataset_id: str,
    script_key: str,
    script_sha256: str,
    base_architecture: str,
    input_size: str
) -> None:
    """Executes compile-and-deploy pipeline.

    Spawns model compilation request via Compilation Service gRPC, polls Redis
    completion keys for status updates, generates presigned URLs for scripts and
    compiled models, and dispatches the deploy command via MQTT.

    Args:
        ctx: Worker connection context state mapping.
        dep_id: Deployment UUID identifier.
        model_id: Model database UUID.
        device_id: Target edge device UUID.
        script_id: Custom script UUID.
        hardware_type: Target hardware compiler platform.
        source_key: Raw input weights key in MinIO.
        dataset_id: Associated dataset UUID.
        script_key: Python script path key in MinIO.
        script_sha256: Script hash code.
        base_architecture: Parent model weights settings.
        input_size: Resolution.
    """
    try:
        logger.info(f"Asynchronously compiling model {model_id} for device {device_id} (hw: {hardware_type})")
        redis = ctx["redis"]
        
        if await redis.exists(f"cancel:deploy:{dep_id}"):
            logger.info(f"Deployment {dep_id} was cancelled before starting. Deleting from DB...")
            async with ctx["session_factory"]() as s:
                dep = await s.get(Deployment, dep_id)
                if dep:
                    await s.delete(dep)
                    await s.commit()
            await redis.delete(f"cancel:deploy:{dep_id}")
            return
 
        try:
            dv = await ctx["ai_stub"].GetDataset(ai_pb2.GetDatasetRequest(id=dataset_id))
        except Exception as e:
            logger.error(f"Failed to get dataset details for dataset {dataset_id}: {e}")
            async with ctx["session_factory"]() as s:
                dep = await s.get(Deployment, dep_id)
                if dep:
                    await DeploymentRepository(s).mark_failed(dep, f"Failed to retrieve dataset details: {e}")
            return
 
        skip_compile = False
        async with ctx["session_factory"]() as s:
            model = await s.get(ModelRef, model_id)
            if model:
                if model.hardware_type == hardware_type and model.compile_status in ("compiling", "ready"):
                    skip_compile = True
                else:
                    from app.models.orm import ModelCompilationRef
                    from sqlalchemy import select
                    res = await s.execute(
                        select(ModelCompilationRef)
                        .where(ModelCompilationRef.model_id == model_id)
                        .where(ModelCompilationRef.hardware_type == hardware_type)
                        .where(ModelCompilationRef.compile_status.in_(["compiling", "ready"]))
                    )
                    comp = res.scalar_one_or_none()
                    if comp:
                        skip_compile = True
                if skip_compile:
                    logger.info(f"Model {model_id} is already compiling/ready for {hardware_type}. Skipping CompileModel.")

        if not skip_compile:
            await redis.delete(f"model_compile_done:{model_id}")
            try:
                comp_res = await ctx["comp_stub"].CompileModel(compilation_pb2.CompileModelRequest(
                    model_id=model_id,
                    source_key=source_key,
                    hardware_type=hardware_type,
                    dataset_id=dataset_id,
                    dataset_key=dv.object_key,
                    base_architecture=base_architecture,
                    input_size=input_size,
                ))
                if comp_res.status == "failed":
                    logger.error(f"Compilation service rejected build: {comp_res.error}")
                    async with ctx["session_factory"]() as s:
                        dep = await s.get(Deployment, dep_id)
                        if dep:
                            await DeploymentRepository(s).mark_failed(dep, f"Compilation failed: {comp_res.error}")
                    return
            except Exception as e:
                logger.error(f"Failed to call compilation service: {e}")
                async with ctx["session_factory"]() as s:
                    dep = await s.get(Deployment, dep_id)
                    if dep:
                        await DeploymentRepository(s).mark_failed(dep, f"Compilation call error: {e}")
                return

        pubsub_key = f"model_compile_done:{model_id}"

        success = False
        error_msg = "Timeout waiting for compilation to finish"

        deadline = asyncio.get_event_loop().time() + 7200
        while asyncio.get_event_loop().time() < deadline:
            if await redis.exists(f"cancel:deploy:{dep_id}"):
                logger.info(f"Deployment {dep_id} was cancelled. Deleting from DB...")
                async with ctx["session_factory"]() as s:
                    dep = await s.get(Deployment, dep_id)
                    if dep:
                        await s.delete(dep)
                        await s.commit()
                await redis.delete(f"cancel:deploy:{dep_id}")
                return

            result = await redis.get(pubsub_key)
            if result:
                result_str = result.decode() if isinstance(result, bytes) else result
                if result_str == "ready":
                    success = True
                    break
                elif result_str.startswith("failed:"):
                    success = False
                    error_msg = result_str[7:]
                    break
            await asyncio.sleep(10)
        else:
            success = False

        if not success:
            logger.error(f"Compilation failed or timed out: {error_msg}")
            async with ctx["session_factory"]() as s:
                dep = await s.get(Deployment, dep_id)
                if dep:
                    await DeploymentRepository(s).mark_failed(dep, error_msg)
            return

        compiled_key = ""
        compiled_sha256 = ""
        async with ctx["session_factory"]() as s:
            model = await s.get(ModelRef, model_id)
            if model:
                if model.hardware_type == hardware_type and model.compiled_key:
                    compiled_key = model.compiled_key
                    compiled_sha256 = model.compiled_sha256
                else:
                    from app.models.orm import ModelCompilationRef
                    from sqlalchemy import select
                    res = await s.execute(
                        select(ModelCompilationRef)
                        .where(ModelCompilationRef.model_id == model_id)
                        .where(ModelCompilationRef.hardware_type == hardware_type)
                        .where(ModelCompilationRef.compile_status == "ready")
                    )
                    comp = res.scalar_one_or_none()
                    if comp:
                        compiled_key = comp.compiled_key
                        compiled_sha256 = comp.compiled_sha256
            else:
                logger.error(f"Model {model_id} not found in DB after compilation")
                dep = await s.get(Deployment, dep_id)
                if dep:
                    await DeploymentRepository(s).mark_failed(dep, "Model ref not found in DB")
                return

        if not compiled_key:
            try:
                m_details = await ctx["ai_stub"].GetModel(ai_pb2.GetModelRequest(id=model_id))
                compiled_key = m_details.compiled_key
                compiled_sha256 = m_details.compiled_sha256
            except Exception as e:
                logger.exception(f"Failed to fetch model details from AI service: {e}")

        model_url = await presigned_url("compiled", compiled_key)
        script_url = await presigned_url("scripts", script_key)

        class_names = []
        if dv and dv.metadata:
            try:
                ds_meta = json.loads(dv.metadata)
                class_names = ds_meta.get("class_names", [])
            except Exception as ex:
                logger.warning(f"Could not parse dataset metadata for class names: {ex}")

        command = {
            "command": "deploy",
            "deployment_id": dep_id,
            "model_url": model_url,
            "model_sha256": compiled_sha256,
            "script_url": script_url,
            "script_sha256": script_sha256,
            "class_names": class_names,
        }

        s_conf = get_settings()
        async with aiomqtt.Client(hostname=s_conf.mqtt_host, port=s_conf.mqtt_port) as client:
            await client.publish(f"device/{device_id}/commands", json.dumps(command))
        
        async with ctx["session_factory"]() as s:
            dep = await s.get(Deployment, dep_id)
            if dep:
                await DeploymentRepository(s).mark_sent(dep)
        logger.info(f"Model compiled successfully. Deploy command sent to device {device_id} for deployment {dep_id}")

    except Exception as e:
        logger.exception(f"Unexpected error in compile & deploy worker: {e}")
        async with ctx["session_factory"]() as s:
            dep = await s.get(Deployment, dep_id)
            if dep:
                await DeploymentRepository(s).mark_failed(dep, f"Internal deploy worker error: {e}")


class WorkerSettings:
    """ARQ Worker configuration class defining tasks and lifecycle hooks."""
    
    functions = [compile_and_deploy_job]
    """List of registered execution tasks."""
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    """Redis settings derived from environment variables."""
    queue_name = "deployment_queue"
    """Name of the worker broker queue."""
    max_jobs = 10
    """Maximum concurrent runs allowed on this worker process."""
    job_timeout = 14400
    """Duration threshold in seconds before a task is forced to terminate."""
    keep_result = 3600
    """Duration in seconds to preserve the task result definition in Redis."""

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        """Connects gRPC, MinIO, and Redis client singletons at worker process startup.

        Args:
            ctx: Shared connection dictionary context.
        """
        from app.config import get_settings
        from shared.utils.minio import init_minio, ensure_buckets
        from shared.utils.database import build_engine, build_session_factory
        from shared.proto_gen import ai_pb2_grpc, compilation_pb2_grpc
        import grpc
        import redis.asyncio as aioredis

        s = get_settings()

        init_minio(s.minio_endpoint, s.minio_access_key, s.minio_secret_key,
                   s.minio_secure, {"compiled": s.minio_bucket_compiled,
                                    "scripts": s.minio_bucket_scripts})

        engine = build_engine(s.postgres_dsn)
        ctx["session_factory"] = build_session_factory(engine)

        ai_channel = grpc.aio.insecure_channel(s.ai_service_grpc)
        comp_channel = grpc.aio.insecure_channel(s.compilation_service_grpc)
        ctx["ai_stub"]   = ai_pb2_grpc.AIServiceStub(ai_channel)
        ctx["comp_stub"] = compilation_pb2_grpc.CompilationServiceStub(comp_channel)
        ctx["ai_channel"]   = ai_channel
        ctx["comp_channel"] = comp_channel

        ctx["redis"] = aioredis.from_url(s.redis_url)

    @staticmethod
    async def on_shutdown(ctx: dict) -> None:
        """Closes gRPC and Redis connection pool clients at worker process shutdown.

        Args:
            ctx: Shared connection dictionary context.
        """
        for key in ("ai_channel", "comp_channel"):
            if key in ctx:
                await ctx[key].close()
        if "redis" in ctx:
            await ctx["redis"].close()
