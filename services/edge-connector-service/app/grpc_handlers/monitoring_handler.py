"""Edge Connector Service gRPC handler managing system telemetry.

Resolves RPC queries fetching active CPU/RAM allocations, coordinates, and YOLO
inference history from MongoDB collections.
"""
import grpc
from app.repositories.monitoring import MonitoringRepository
from shared.proto_gen import monitoring_pb2, monitoring_pb2_grpc

def _state_to_proto(s: dict) -> monitoring_pb2.DeviceStateResponse:
    """Formats a dictionary representation of device state into a Protobuf message.

    Args:
        s: State values mapping dictionary.

    Returns:
        The populated DeviceStateResponse Protobuf object.
    """
    res = monitoring_pb2.DeviceStateResponse(
        device_id=s.get("device_id", ""),
        status=s.get("status", "offline"),
        active_model_id=s.get("active_model_id", ""),
        active_script_id=s.get("active_script_id", ""),
        active_deployment_id=s.get("active_deployment_id", ""),
        cpu_percent=float(s.get("cpu_percent", 0.0)),
        ram_percent=float(s.get("ram_percent", 0.0)),
        ram_used_mb=float(s.get("ram_used_mb", 0.0)),
        last_seen_at=s.get("last_seen_at", ""),
        latency_ms=float(s.get("latency_ms", 0.0)),
    )
    if "coordinates" in s and s["coordinates"]:
        res.coordinates.extend(s["coordinates"])
    return res

class MonitoringServiceHandler(monitoring_pb2_grpc.MonitoringServiceServicer):
    """gRPC Service Servicer implementing telemetry monitoring retrieval."""

    def __init__(self, repo_factory: callable):
        """Initializes the Monitoring Service Handler.

        Args:
            repo_factory: Callable returning an active MonitoringRepository.
        """
        self._repo_factory = repo_factory

    async def GetDeviceState(
        self, req: monitoring_pb2.GetDeviceStateRequest, ctx: grpc.aio.ServicerContext
    ) -> monitoring_pb2.DeviceStateResponse:
        """Retrieves telemetry status and resource allocations for a device.

        Args:
            req: Target device ID request.
            ctx: gRPC connection context.

        Returns:
            DeviceStateResponse message.
        """
        repo = self._repo_factory()
        state = await repo.get_device_state(req.device_id)
        if not state:
            await ctx.abort(grpc.StatusCode.NOT_FOUND, "No state for this device")
            return
        return _state_to_proto(state)

    async def ListDeviceStates(
        self, req: monitoring_pb2.ListDeviceStatesRequest, ctx: grpc.aio.ServicerContext
    ) -> monitoring_pb2.ListDeviceStatesResponse:
        """Lists current status telemetry for all active devices.

        Args:
            req: Empty query message.
            ctx: gRPC connection context.

        Returns:
            ListDeviceStatesResponse message.
        """
        repo = self._repo_factory()
        states = await repo.list_device_states()
        return monitoring_pb2.ListDeviceStatesResponse(states=[_state_to_proto(s) for s in states])

    async def GetInferenceResults(
        self, req: monitoring_pb2.GetInferenceResultsRequest, ctx: grpc.aio.ServicerContext
    ) -> monitoring_pb2.GetInferenceResultsResponse:
        """Lists historical inference result JSON packets captured by a device.

        Args:
            req: Target device and query limit count request.
            ctx: gRPC connection context.

        Returns:
            GetInferenceResultsResponse message.
        """
        repo = self._repo_factory()
        results = await repo.get_inference_results(req.device_id, req.limit or 20)
        protos = [monitoring_pb2.InferenceResult(
            device_id=r["device_id"], deployment_id=r.get("deployment_id", ""),
            timestamp=r["timestamp"], result_json=r["result_json"],
        ) for r in results]
        return monitoring_pb2.GetInferenceResultsResponse(results=protos)

    async def DeleteDeviceState(
        self, req: monitoring_pb2.DeleteDeviceStateRequest, ctx: grpc.aio.ServicerContext
    ) -> monitoring_pb2.DeleteDeviceStateResponse:
        """Wipes historical logs and telemetry mappings for a specific device from MongoDB.

        Args:
            req: Target device ID.
            ctx: gRPC connection context.

        Returns:
            DeleteDeviceStateResponse indicator.
        """
        repo = self._repo_factory()
        await repo.delete_device_data(req.device_id)
        return monitoring_pb2.DeleteDeviceStateResponse(success=True)
