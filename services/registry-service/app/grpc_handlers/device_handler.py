"""Registry Service gRPC handler for managing edge devices metadata.

Handles registration, metadata updates, status heartbeats, and deletion of
IoT devices in the PostgreSQL database.
"""
import grpc
from sqlalchemy.ext.asyncio import async_sessionmaker
from shared.proto_gen import device_pb2, device_pb2_grpc
from app.repositories.devices import DeviceRepository

def _to_proto(d) -> device_pb2.DeviceResponse:
    """Formats an ORM Device record to its corresponding Protobuf message type.

    Args:
        d: The ORM Device entity instance.

    Returns:
        The populated DeviceResponse Protobuf object.
    """
    res = device_pb2.DeviceResponse(
        id=d.id, name=d.name, hardware_type=d.hardware_type,
        description=d.description or "", status=d.status,
        last_seen_at=d.last_seen_at.isoformat() if d.last_seen_at else "",
        created_at=d.created_at.isoformat(),
    )
    if hasattr(d, 'sensors') and d.sensors:
        res.sensors.extend(d.sensors)
    if hasattr(d, 'actuators') and d.actuators:
        res.actuators.extend(d.actuators)
    if hasattr(d, 'others') and d.others:
        res.others.extend(d.others)
    return res

class DeviceServiceHandler(device_pb2_grpc.DeviceServiceServicer):
    """gRPC Service Servicer handling edge device lifecycle actions."""

    def __init__(self, sf: async_sessionmaker):
        """Initializes the Device Service Handler.

        Args:
            sf: Database async session maker class.
        """
        self._sf = sf

    async def CreateDevice(self, req: device_pb2.CreateDeviceRequest, ctx: grpc.aio.ServicerContext) -> device_pb2.DeviceResponse:
        """Registers a new edge device.

        Args:
            req: Device registration parameters request.
            ctx: gRPC connection context.

        Returns:
            The created DeviceResponse.
        """
        async with self._sf() as s:
            d = await DeviceRepository(s).create(
                req.name, req.hardware_type, req.description or None,
                list(req.sensors), list(req.actuators), list(req.others)
            )
            return _to_proto(d)

    async def GetDevice(self, req: device_pb2.GetDeviceRequest, ctx: grpc.aio.ServicerContext) -> device_pb2.DeviceResponse:
        """Retrieves a single registered device by its ID.

        Args:
            req: Target device ID query request.
            ctx: gRPC connection context.

        Returns:
            DeviceResponse details.
        """
        async with self._sf() as s:
            d = await DeviceRepository(s).get(req.id)
            if not d:
                ctx.abort(grpc.StatusCode.NOT_FOUND, "Device not found")
                return
            return _to_proto(d)

    async def ListDevices(self, req: device_pb2.ListDevicesRequest, ctx: grpc.aio.ServicerContext) -> device_pb2.ListDevicesResponse:
        """Lists all registered edge devices.

        Args:
            req: Empty query request message.
            ctx: gRPC connection context.

        Returns:
            ListDevicesResponse containing devices.
        """
        async with self._sf() as s:
            devices = await DeviceRepository(s).list_all()
            return device_pb2.ListDevicesResponse(devices=[_to_proto(d) for d in devices])

    async def DeleteDevice(self, req: device_pb2.DeleteDeviceRequest, ctx: grpc.aio.ServicerContext) -> device_pb2.DeleteDeviceResponse:
        """Deletes a device from the database catalog.

        Args:
            req: Target device ID.
            ctx: gRPC connection context.

        Returns:
            DeleteDeviceResponse indicator.
        """
        async with self._sf() as s:
            ok = await DeviceRepository(s).delete(req.id)
            if not ok:
                ctx.abort(grpc.StatusCode.NOT_FOUND, "Device not found")
                return
            return device_pb2.DeleteDeviceResponse(success=True)

    async def UpdateDeviceStatus(self, req: device_pb2.UpdateDeviceStatusRequest, ctx: grpc.aio.ServicerContext) -> device_pb2.DeviceResponse:
        """Updates the status and last seen timestamp of a device.

        Args:
            req: Status update parameters.
            ctx: gRPC connection context.

        Returns:
            Updated DeviceResponse.
        """
        async with self._sf() as s:
            d = await DeviceRepository(s).update_status(req.id, req.status)
            if not d:
                ctx.abort(grpc.StatusCode.NOT_FOUND, "Device not found")
                return
            return _to_proto(d)

    async def UpdateDevice(self, req: device_pb2.UpdateDeviceRequest, ctx: grpc.aio.ServicerContext) -> device_pb2.DeviceResponse:
        """Updates description and name of an edge device.

        Args:
            req: Update metadata parameters.
            ctx: gRPC connection context.

        Returns:
            Updated DeviceResponse.
        """
        async with self._sf() as s:
            d = await DeviceRepository(s).update(req.id, req.name, req.description or None)
            if not d:
                ctx.abort(grpc.StatusCode.NOT_FOUND, "Device not found")
                return
            return _to_proto(d)
