"""Edge Connector Service gRPC handler managing model OTA deployments.

Triggers compiling, serializing, signing download URLs, enqueuing build workers,
and publishing command packets via MQTT topics to target devices.
"""
import asyncio
import json
import logging
import grpc
import aiomqtt
from arq import create_pool
from arq.connections import RedisSettings
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import async_sessionmaker
from shared.proto_gen import (
    deployment_pb2, deployment_pb2_grpc,
    ai_pb2, ai_pb2_grpc,
    compilation_pb2, compilation_pb2_grpc
)
from shared.utils.minio import presigned_url
from app.repositories.deployments import DeploymentRepository
from app.models.orm import Deployment, ModelRef

logger = logging.getLogger(__name__)
"""Logger instance specific to deployment handlers."""

def _to_proto(d) -> deployment_pb2.DeploymentResponse:
    """Formats an ORM Deployment record to its corresponding Protobuf message type.

    Args:
        d: The ORM Deployment entity instance.

    Returns:
        The populated DeploymentResponse Protobuf object.
    """
    return deployment_pb2.DeploymentResponse(
        id=d.id, device_id=d.device_id, model_id=d.model_id, script_id=d.script_id,
        status=d.status,
        sent_at=d.sent_at.isoformat() if d.sent_at else "",
        running_at=d.running_at.isoformat() if d.running_at else "",
        error_msg=d.error_msg or "",
        created_at=d.created_at.isoformat(),
        name=d.name or "",
    )

class DeploymentServiceHandler(deployment_pb2_grpc.DeploymentServiceServicer):
    """gRPC Service Servicer implementing edge deployment orchestration."""

    def __init__(self, sf: async_sessionmaker, mqtt_host: str, mqtt_port: int,
                 ai_service_grpc: str, compilation_service_grpc: str, redis_url: str):
        """Initializes the Deployment Service Handler.

        Args:
            sf: SQLAlchemy session factory.
            mqtt_host: Hostname of the MQTT broker.
            mqtt_port: Network port of the MQTT broker.
            ai_service_grpc: Registry/AI service endpoint address.
            compilation_service_grpc: Compilation service endpoint address.
            redis_url: Connection settings for the task worker queue.
        """
        self._sf = sf
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._ai_service_grpc = ai_service_grpc
        self._compilation_service_grpc = compilation_service_grpc
        self._redis_settings = RedisSettings.from_dsn(redis_url)
        self._redis_pool = None
        self._ai_channel = grpc.aio.insecure_channel(ai_service_grpc)
        self._ai_stub = ai_pb2_grpc.AIServiceStub(self._ai_channel)

    async def _get_pool(self) -> any:
        """Retrieves or initializes the task queue broker pool.

        Returns:
            ARQ Redis connection pool.
        """
        if self._redis_pool is None:
            self._redis_pool = await create_pool(self._redis_settings, default_queue_name="deployment_queue")
        return self._redis_pool

    async def CreateDeployment(
        self, req: deployment_pb2.CreateDeploymentRequest, ctx: grpc.aio.ServicerContext
    ) -> deployment_pb2.DeploymentResponse:
        """Triggers a deployment run, enqueuing compilation first if target binary is missing.

        Args:
            req: Target model, script, and device information request.
            ctx: gRPC connection context.

        Returns:
            DeploymentResponse message details.
        """
        async with self._sf() as s:
            repo = DeploymentRepository(s)
            device = await repo.get_device(req.device_id)
            if not device:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Device not found")
                return
            model = await repo.get_model(req.model_id)
            if not model:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Model not found")
                return
            script = await repo.get_script(req.script_id)
            if not script:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Script not found")
                return

            compilation_ready = False
            compiled_key = ""
            compiled_sha256 = ""

            if model.hardware_type == device.hardware_type and model.compile_status == "ready":
                compilation_ready = True
                compiled_key = model.compiled_key
                compiled_sha256 = model.compiled_sha256
            else:
                from app.models.orm import ModelCompilationRef
                from sqlalchemy import select
                res = await s.execute(
                    select(ModelCompilationRef)
                    .where(ModelCompilationRef.model_id == req.model_id)
                    .where(ModelCompilationRef.hardware_type == device.hardware_type)
                    .where(ModelCompilationRef.compile_status == "ready")
                )
                comp = res.scalar_one_or_none()
                if comp:
                    compilation_ready = True
                    compiled_key = comp.compiled_key
                    compiled_sha256 = comp.compiled_sha256

            if compilation_ready:
                dep = await repo.create(req.device_id, req.model_id, req.script_id, name=req.name)
                model_url = await presigned_url("compiled", compiled_key)
                script_url = await presigned_url("scripts", script.script_key)

                class_names = []
                if model.dataset_id:
                    try:
                        ds_resp = await self._ai_stub.GetDataset(ai_pb2.GetDatasetRequest(id=model.dataset_id))
                        if ds_resp.metadata:
                            ds_meta = json.loads(ds_resp.metadata)
                            class_names = ds_meta.get("class_names", [])
                    except Exception as ex:
                        logger.warning(f"Could not retrieve dataset metadata for class names: {ex}")

                command = {
                    "command": "deploy",
                    "deployment_id": dep.id,
                    "model_url": model_url,
                    "model_sha256": compiled_sha256,
                    "script_url": script_url,
                    "script_sha256": script.script_sha256,
                    "class_names": class_names,
                }
                try:
                    async with aiomqtt.Client(hostname=self._mqtt_host, port=self._mqtt_port) as client:
                        await client.publish(f"device/{req.device_id}/commands", json.dumps(command))
                    await repo.mark_sent(dep)
                    logger.info(f"Deploy command sent → device {req.device_id}, deployment {dep.id}")
                except Exception as e:
                    await repo.mark_failed(dep, str(e))
                    await ctx.abort(grpc.StatusCode.UNAVAILABLE, f"MQTT error: {e}")
                    return

                await s.refresh(dep)
                return _to_proto(dep)
            else:
                if not model.dataset_id:
                    await ctx.abort(
                        grpc.StatusCode.FAILED_PRECONDITION,
                        f"Model {req.model_id} does not have an associated dataset required for compilation."
                    )
                    return

                dep = await repo.create(req.device_id, req.model_id, req.script_id, name=req.name, status="compiling")

                pool = await self._get_pool()
                await pool.enqueue_job(
                    "compile_and_deploy_job",
                    dep_id=dep.id,
                    model_id=req.model_id,
                    device_id=req.device_id,
                    script_id=req.script_id,
                    hardware_type=device.hardware_type,
                    source_key=model.source_key,
                    dataset_id=model.dataset_id,
                    script_key=script.script_key,
                    script_sha256=script.script_sha256,
                    base_architecture=model.base_architecture or "",
                    input_size=model.input_size or "",
                    _job_id=f"deploy:{dep.id}",
                )

                await s.refresh(dep)
                return _to_proto(dep)

    async def _cleanup_cancelled_deployments(self, session: any) -> None:
        """Deletes cancelled compile-and-deploy records enqueued in Redis cancel tables.

        Args:
            session: SQLAlchemy active connection database session.
        """
        try:
            pool = await self._get_pool()
            keys = await pool.keys("cancel:deploy:*")
            if keys:
                for k in keys:
                    dep_id = k.decode().split(":")[-1]
                    dep = await session.get(Deployment, dep_id)
                    if dep:
                        await session.delete(dep)
                    await pool.delete(k)
                await session.commit()
        except Exception as e:
            logger.exception(f"Error in cleanup of cancelled deployments: {e}")

    async def GetDeployment(
        self, req: deployment_pb2.GetDeploymentRequest, ctx: grpc.aio.ServicerContext
    ) -> deployment_pb2.DeploymentResponse:
        """Retrieves details of a single deployment record by its ID.

        Args:
            req: Target deployment ID request parameters.
            ctx: gRPC connection context.

        Returns:
            DeploymentResponse message.
        """
        async with self._sf() as s:
            await self._cleanup_cancelled_deployments(s)
            d = await DeploymentRepository(s).get(req.id)
            if not d:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Deployment not found")
                return
            return _to_proto(d)

    async def ListDeployments(
        self, req: deployment_pb2.ListDeploymentsRequest, ctx: grpc.aio.ServicerContext
    ) -> deployment_pb2.ListDeploymentsResponse:
        """Retrieves details of all deployment records.

        Args:
            req: Empty query message.
            ctx: gRPC connection context.

        Returns:
            ListDeploymentsResponse message.
        """
        async with self._sf() as s:
            await self._cleanup_cancelled_deployments(s)
            deps = await DeploymentRepository(s).list_all()
            return deployment_pb2.ListDeploymentsResponse(deployments=[_to_proto(d) for d in deps])

    async def ListDeviceDeployments(
        self, req: deployment_pb2.ListDeviceDeploymentsRequest, ctx: grpc.aio.ServicerContext
    ) -> deployment_pb2.ListDeploymentsResponse:
        """Retrieves details of all deployment records scheduled on a device.

        Args:
            req: Target device ID.
            ctx: gRPC connection context.

        Returns:
            ListDeploymentsResponse message.
        """
        async with self._sf() as s:
            await self._cleanup_cancelled_deployments(s)
            deps = await DeploymentRepository(s).list_for_device(req.device_id)
            return deployment_pb2.ListDeploymentsResponse(deployments=[_to_proto(d) for d in deps])
