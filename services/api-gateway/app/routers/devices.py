"""REST API Router for managing devices.

Exposes REST endpoints to create, read, update, list, and delete physical
or virtual devices, and queries supported catalogs from downstream services.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.auth.jwt import verify_token
from app.stubs import get_stub
from shared.proto_gen import device_pb2

router = APIRouter(prefix="/api/devices", tags=["devices"])
"""APIRouter instance for device endpoints."""

class DeviceCreate(BaseModel):
    """Pydantic request body schema for creating a new device."""
    name: str
    """User-defined human readable name for the device."""
    hardware_type: str
    """Target hardware architecture identifier (e.g. 'rpi', 'hailo8')."""
    description: str = ""
    """Optional text details or comments describing the device."""
    sensors: list[str] = []
    """Optional list of sensor driver ids connected to the device."""
    actuators: list[str] = []
    """Optional list of actuator driver ids connected to the device."""
    others: list[str] = []
    """Optional list of other device peripheral driver ids."""

class DeviceUpdate(BaseModel):
    """Pydantic request body schema for updating device metadata."""
    name: str
    """New name for the device."""
    description: str = ""
    """New description text for the device."""

@router.post("", status_code=201)
async def create_device(body: DeviceCreate, _=Depends(verify_token)) -> dict:
    """Registers a new edge device in the database metadata registry.

    Args:
        body: The parameters of the device to be registered.

    Returns:
        JSON response with the registered device details.
    """
    stub = get_stub("device")
    r = await stub.CreateDevice(device_pb2.CreateDeviceRequest(
        name=body.name, hardware_type=body.hardware_type, description=body.description,
        sensors=body.sensors, actuators=body.actuators, others=body.others))
    return {"id": r.id, "name": r.name, "hardware_type": r.hardware_type,
            "description": r.description, "status": r.status, "created_at": r.created_at,
            "sensors": list(r.sensors), "actuators": list(r.actuators), "others": list(r.others)}

@router.get("")
async def list_devices(_=Depends(verify_token)) -> list[dict]:
    """Retrieves all registered devices and their connectivity statuses.

    Returns:
        List of device dictionary representations.
    """
    stub = get_stub("device")
    r = await stub.ListDevices(device_pb2.ListDevicesRequest())
    return [{"id": d.id, "name": d.name, "hardware_type": d.hardware_type,
             "description": d.description, "status": d.status, "last_seen_at": d.last_seen_at, "created_at": d.created_at,
             "sensors": list(d.sensors), "actuators": list(d.actuators), "others": list(d.others)}
            for d in r.devices]

@router.get("/hardware-types")
async def get_hardware_types(_=Depends(verify_token)) -> list[str]:
    """Lists all valid compilation target platforms.

    Returns:
        List of hardware target strings.
    """
    from shared.proto_gen import compilation_pb2
    stub = get_stub("compilation")
    r = await stub.GetSupportedHardware(compilation_pb2.GetSupportedHardwareRequest())
    return list(r.hardware_types)

@router.get("/sensors")
async def get_sensors(_=Depends(verify_token)) -> list[str]:
    """Lists all supported sensor driver identifiers.

    Returns:
        List of sensor module strings.
    """
    from shared.proto_gen import compilation_pb2
    stub = get_stub("compilation")
    r = await stub.GetSupportedSensors(compilation_pb2.GetSupportedSensorsRequest())
    return list(r.sensors)

@router.get("/actuators")
async def get_actuators(_=Depends(verify_token)) -> list[str]:
    """Lists all supported actuator driver identifiers.

    Returns:
        List of actuator module strings.
    """
    from shared.proto_gen import compilation_pb2
    stub = get_stub("compilation")
    r = await stub.GetSupportedActuators(compilation_pb2.GetSupportedActuatorsRequest())
    return list(r.actuators)

@router.get("/others")
async def get_others(_=Depends(verify_token)) -> list[str]:
    """Lists other auxiliary peripheral driver identifiers.

    Returns:
        List of other module strings.
    """
    from shared.proto_gen import compilation_pb2
    stub = get_stub("compilation")
    r = await stub.GetSupportedOthers(compilation_pb2.GetSupportedOthersRequest())
    return list(r.others)

@router.get("/labels")
async def get_all_labels(_=Depends(verify_token)) -> dict[str, str]:
    """Combines human-readable UI label descriptors for all peripherals.

    Returns:
        A combined dictionary mapping hardware IDs to human readable names.
    """
    from shared.proto_gen import compilation_pb2
    stub = get_stub("compilation")
    
    hw_res = await stub.GetSupportedHardware(compilation_pb2.GetSupportedHardwareRequest())
    sensor_res = await stub.GetSupportedSensors(compilation_pb2.GetSupportedSensorsRequest())
    actuator_res = await stub.GetSupportedActuators(compilation_pb2.GetSupportedActuatorsRequest())
    other_res = await stub.GetSupportedOthers(compilation_pb2.GetSupportedOthersRequest())
    
    merged = {}
    merged.update(dict(hw_res.labels))
    merged.update(dict(sensor_res.labels))
    merged.update(dict(actuator_res.labels))
    merged.update(dict(other_res.labels))
    return merged

@router.get("/{device_id}")
async def get_device(device_id: str, _=Depends(verify_token)) -> dict:
    """Retrieves metadata of a specific device by its registered ID.

    Args:
        device_id: Unique hash id of the device.

    Returns:
        Device dictionary details.
    """
    stub = get_stub("device")
    r = await stub.GetDevice(device_pb2.GetDeviceRequest(id=device_id))
    return {"id": r.id, "name": r.name, "hardware_type": r.hardware_type,
            "description": r.description, "status": r.status, "created_at": r.created_at,
            "sensors": list(r.sensors), "actuators": list(r.actuators), "others": list(r.others)}

@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: str, _=Depends(verify_token)) -> None:
    """Deletes a device from the database and cleans up telemetry states.

    Args:
        device_id: Target device unique identifier.
    """
    await get_stub("device").DeleteDevice(device_pb2.DeleteDeviceRequest(id=device_id))
    try:
        from shared.proto_gen import monitoring_pb2
        await get_stub("monitoring").DeleteDeviceState(
            monitoring_pb2.DeleteDeviceStateRequest(device_id=device_id)
        )
    except Exception as e:
        import logging
        logging.getLogger("api-gateway").error(f"Failed to delete monitoring state for device {device_id}: {e}")

@router.put("/{device_id}")
async def update_device(device_id: str, body: DeviceUpdate, _=Depends(verify_token)) -> dict:
    """Updates name and description metadata fields for a specific device.

    Args:
        device_id: Unique ID of the device.
        body: The updated metadata parameter fields.

    Returns:
        The updated device details dictionary.
    """
    stub = get_stub("device")
    r = await stub.UpdateDevice(device_pb2.UpdateDeviceRequest(
        id=device_id, name=body.name, description=body.description))
    return {"id": r.id, "name": r.name, "hardware_type": r.hardware_type,
            "description": r.description, "status": r.status, "created_at": r.created_at,
            "sensors": list(r.sensors), "actuators": list(r.actuators), "others": list(r.others)}
