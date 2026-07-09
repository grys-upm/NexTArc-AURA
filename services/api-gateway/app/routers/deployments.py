"""REST API Router for managing OTA deployments.

Exposes REST endpoints to schedule new deployments, list active and historical
deployments, and cancel pending deployment tasks.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
import redis.asyncio as aioredis
from app.auth.jwt import verify_token
from app.stubs import get_stub
from shared.proto_gen import deployment_pb2

router = APIRouter(prefix="/api/deployments", tags=["deployments"])
"""APIRouter instance for deployment endpoints."""

class DeployRequest(BaseModel):
    """Pydantic request body schema for scheduling a new OTA deployment."""
    device_id: str
    """Target device UUID identifier."""
    model_id: str
    """Compiled hardware model UUID identifier."""
    script_id: str
    """User inference python script UUID identifier."""
    name: str = ""
    """Human readable label for tracking this specific deployment."""

@router.post("", status_code=201)
async def create_deployment(body: DeployRequest, _=Depends(verify_token)) -> dict:
    """Schedules a new OTA deployment job on the target edge device.

    Args:
        body: The parameters of the model and script to deploy.

    Returns:
        JSON response with the scheduled deployment details.
    """
    d = await get_stub("deployment").CreateDeployment(
        deployment_pb2.CreateDeploymentRequest(
            device_id=body.device_id, model_id=body.model_id, script_id=body.script_id, name=body.name))
    return {"id": d.id, "status": d.status, "sent_at": d.sent_at, "created_at": d.created_at, "name": d.name}

@router.get("")
async def list_deployments(_=Depends(verify_token)) -> list[dict]:
    """Retrieves all scheduled OTA deployments and their execution statuses.

    Returns:
        List of deployment records.
    """
    r = await get_stub("deployment").ListDeployments(deployment_pb2.ListDeploymentsRequest())
    return [{"id": d.id, "device_id": d.device_id, "model_id": d.model_id,
             "script_id": d.script_id, "status": d.status, "error_msg": d.error_msg, "created_at": d.created_at, "name": d.name}
            for d in r.deployments]

@router.get("/device/{device_id}")
async def list_device_deployments(device_id: str, _=Depends(verify_token)) -> list[dict]:
    """Retrieves all historical and active OTA deployments for a specific device.

    Args:
        device_id: Target device identifier.

    Returns:
        List of deployments for that device.
    """
    r = await get_stub("deployment").ListDeviceDeployments(
        deployment_pb2.ListDeviceDeploymentsRequest(device_id=device_id))
    return [{"id": d.id, "model_id": d.model_id, "script_id": d.script_id,
             "status": d.status, "error_msg": d.error_msg, "running_at": d.running_at, "created_at": d.created_at, "name": d.name}
            for d in r.deployments]

@router.get("/{deployment_id}")
async def get_deployment(deployment_id: str, _=Depends(verify_token)) -> dict:
    """Retrieves detailed logs and status metrics of a specific deployment job.

    Args:
        deployment_id: Unique identifier for the deployment.

    Returns:
        The deployment detailed record.
    """
    d = await get_stub("deployment").GetDeployment(
        deployment_pb2.GetDeploymentRequest(id=deployment_id))
    return {"id": d.id, "device_id": d.device_id, "model_id": d.model_id,
            "script_id": d.script_id, "status": d.status, "error_msg": d.error_msg,
            "sent_at": d.sent_at, "running_at": d.running_at, "created_at": d.created_at, "name": d.name}

@router.delete("/{deployment_id}", status_code=204)
async def delete_deployment(deployment_id: str, _=Depends(verify_token)) -> None:
    """Signals cancellation for a pending or running deployment in the Redis queue.

    Args:
        deployment_id: Unique deployment ID.
    """
    from app.config import get_settings
    s_settings = get_settings()
    try:
        redis_client = aioredis.from_url(s_settings.redis_url)
        await redis_client.set(f"cancel:deploy:{deployment_id}", "1", ex=300)
        await redis_client.close()
    except Exception:
        pass
