"""Unified MQTT event and telemetry listener for the Edge Connector Service.

Subscribes to telemetry, inference payloads, status alerts, and deployment status events.
Provides automatic dynamic peripheral driver library updates sync over the air (OTA).
"""
import io
import os
import json
import logging
import zipfile
import hashlib
import asyncio
import aiomqtt
from pathlib import Path
from prometheus_client import Gauge
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.repositories.deployments import DeploymentRepository
from app.repositories.monitoring import MonitoringRepository
from shared.utils.minio import upload_bytes, presigned_url

logger = logging.getLogger(__name__)
"""Logger instance specific to MQTT listeners."""

CPU_GAUGE = Gauge("aura_device_cpu_percent",    "CPU usage %",    ["device_id"])
"""Prometheus gauge measuring CPU consumption percentage of the edge device."""

RAM_GAUGE = Gauge("aura_device_ram_percent",    "RAM usage %",    ["device_id"])
"""Prometheus gauge measuring RAM consumption percentage of the edge device."""

RAM_MB_GAUGE = Gauge("aura_device_ram_used_mb", "RAM used MB",    ["device_id"])
"""Prometheus gauge measuring RAM usage in megabytes of the edge device."""

_PLATFORM_HW_MTIME_CACHE = 0.0
"""Global cache timestamp tracking maximum hardware directory file modifications."""

_LIBRARIES_DIR_HASH_CACHE = ""
"""Global cache string containing hardware directory content hash."""

_LIBRARIES_ZIP_HASH_CACHE = ""
"""Global cache string containing hardware ZIP archive checksum."""

_LIBRARIES_ZIP_CACHE = b""
"""Global cache bytes containing zipped hardware archive."""

def get_platform_hardware_hash_and_zip() -> tuple[str, str, bytes]:
    """Walks the hardware folder and builds an in-memory ZIP, caching the result.

    Returns:
        A tuple of (directory_content_hash, zip_file_hash, zip_bytes).
    """
    global _PLATFORM_HW_MTIME_CACHE, _LIBRARIES_DIR_HASH_CACHE, _LIBRARIES_ZIP_HASH_CACHE, _LIBRARIES_ZIP_CACHE
    
    hw_dir = Path("/app/hardware")
    if not hw_dir.exists():
        hw_dir = Path("hardware").resolve()

    if not hw_dir.exists():
        return "", "", b""

    max_mtime = 0.0
    for root, dirs, files in os.walk(hw_dir):
        for file in files:
            if "__pycache__" in root or file.endswith(".pyc") or file.endswith(".pyo"):
                continue
            try:
                mtime = os.path.getmtime(os.path.join(root, file))
                if mtime > max_mtime:
                    max_mtime = mtime
            except OSError:
                pass

    if max_mtime == _PLATFORM_HW_MTIME_CACHE and _LIBRARIES_DIR_HASH_CACHE:
        return _LIBRARIES_DIR_HASH_CACHE, _LIBRARIES_ZIP_HASH_CACHE, _LIBRARIES_ZIP_CACHE

    logger.info("[get_platform_hardware_hash_and_zip] Changes detected or initial run. Packaging hardware folder...")
    sha_hash = hashlib.sha256()
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(hw_dir):
            dirs.sort()
            files.sort()
            for file in files:
                if "__pycache__" in root or file.endswith(".pyc") or file.endswith(".pyo"):
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(hw_dir)
                
                zip_file.write(file_path, rel_path)
                
                sha_hash.update(str(rel_path).encode("utf-8"))
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        sha_hash.update(chunk)

    zip_bytes = zip_buffer.getvalue()
    dir_hash = sha_hash.hexdigest()
    zip_hash = hashlib.sha256(zip_bytes).hexdigest()

    _LIBRARIES_DIR_HASH_CACHE = dir_hash
    _LIBRARIES_ZIP_HASH_CACHE = zip_hash
    _LIBRARIES_ZIP_CACHE = zip_bytes
    _PLATFORM_HW_MTIME_CACHE = max_mtime

    return dir_hash, zip_hash, zip_bytes


class EdgeConnectorMQTTListener:
    """Manages active MQTT connections, subscriptions, and message dispatch routines."""

    def __init__(self, mqtt_host: str, mqtt_port: int, sf: async_sessionmaker, mongo_repo_factory: callable):
        """Initializes the Edge Connector MQTT Listener.

        Args:
            mqtt_host: Network address hostname of the broker.
            mqtt_port: Network port of the broker.
            sf: Database session factory creator.
            mongo_repo_factory: Callable returning an active MongoDB repository.
        """
        self._host = mqtt_host
        self._port = mqtt_port
        self._sf = sf
        self._mongo_repo_factory = mongo_repo_factory

    async def start(self) -> None:
        """Launches the listener loop, auto-reconnecting on broker connection failures."""
        logger.info("EdgeConnectorMQTTListener starting")
        while True:
            try:
                async with aiomqtt.Client(hostname=self._host, port=self._port) as client:
                    await client.subscribe("device/+/events")
                    await client.subscribe("device/+/telemetry")
                    await client.subscribe("device/+/inference")
                    await client.subscribe("device/+/status")
                    async for msg in client.messages:
                        try:
                            await self._handle(msg)
                        except Exception as e:
                            logger.exception(f"Error handling message on topic '{msg.topic}': {e}")
            except aiomqtt.MqttError as e:
                logger.warning(f"MQTT error: {e} — retrying in 5s")
                await asyncio.sleep(5)
            except Exception as e:
                logger.exception(f"Unexpected error in MQTT listener: {e} — retrying in 5s")
                await asyncio.sleep(5)

    async def _handle(self, msg: aiomqtt.Message) -> None:
        """Decodes JSON packet content and routes to the appropriate message type handler.

        Args:
            msg: The raw incoming MQTT message object.
        """
        try:
            payload = json.loads(msg.payload)
        except Exception:
            return

        topic = str(msg.topic)
        parts = topic.split("/")
        device_id = parts[1]

        if topic.endswith("/telemetry"):
            await self._handle_telemetry(device_id, payload)
        elif topic.endswith("/inference"):
            await self._handle_inference(device_id, payload)
        elif topic.endswith("/events"):
            await self._handle_event(payload)
        elif topic.endswith("/status"):
            await self._handle_status(device_id, payload)

    async def _handle_telemetry(self, device_id: str, payload: dict) -> None:
        """Saves telemetry resource percentages to MongoDB and updates Prometheus metrics.

        Args:
            device_id: Target device identifier.
            payload: Parsed telemetry properties mapping.
        """
        mongo_repo = self._mongo_repo_factory()
        await mongo_repo.upsert_device_state(device_id, {
            "status": "online",
            "cpu_percent": payload.get("cpu_percent", 0.0),
            "ram_percent": payload.get("ram_percent", 0.0),
            "ram_used_mb": payload.get("ram_used_mb", 0.0),
            "latency_ms": payload.get("latency_ms", 0.0),
            "active_model_id": payload.get("active_model_id", ""),
            "active_script_id": payload.get("active_script_id", ""),
            "active_deployment_id": payload.get("active_deployment_id", ""),
            "coordinates": payload.get("coordinates", []),
        })

        try:
            from shared.proto_gen import device_pb2, device_pb2_grpc
            from app.config import get_settings
            import grpc
            s_cfg = get_settings()
            target_grpc = getattr(s_cfg, "device_service_grpc", s_cfg.ai_service_grpc)
            async with grpc.aio.insecure_channel(target_grpc) as channel:
                stub = device_pb2_grpc.DeviceServiceStub(channel)
                await stub.UpdateDeviceStatus(
                    device_pb2.UpdateDeviceStatusRequest(id=device_id, status="online")
                )
        except Exception as e:
            logger.error(f"Failed to update device status in registry for '{device_id}': {e}")

        CPU_GAUGE.labels(device_id=device_id).set(payload.get("cpu_percent", 0.0))
        RAM_GAUGE.labels(device_id=device_id).set(payload.get("ram_percent", 0.0))
        RAM_MB_GAUGE.labels(device_id=device_id).set(payload.get("ram_used_mb", 0.0))

        device_hash = payload.get("libraries_hash", "")
        platform_dir_hash, platform_zip_hash, zip_bytes = get_platform_hardware_hash_and_zip()

        if not platform_dir_hash:
            return

        if device_hash != platform_dir_hash:
            logger.info(
                f"Device '{device_id}' libraries hash mismatch. "
                f"Device: '{device_hash}', Platform: '{platform_dir_hash}'. Triggering sync."
            )
            object_key = f"libraries/{platform_zip_hash}.zip"
            try:
                await upload_bytes("compiled", object_key, zip_bytes)
                url = await presigned_url("compiled", object_key)

                command = {
                    "command": "update_libraries",
                    "libraries_url": url,
                    "libraries_sha256": platform_zip_hash,
                    "directory_sha256": platform_dir_hash
                }
                async with aiomqtt.Client(hostname=self._host, port=self._port) as client:
                    await client.publish(f"device/{device_id}/commands", json.dumps(command))
                logger.info(f"Published update_libraries command to device '{device_id}' successfully")
            except Exception as e:
                logger.error(f"Failed to trigger libraries sync for device '{device_id}': {e}")

    async def _handle_inference(self, device_id: str, payload: dict) -> None:
        """Saves a YOLO inference prediction JSON log entry to MongoDB.

        Args:
            device_id: Source device identifier.
            payload: Parsed inference result properties.
        """
        mongo_repo = self._mongo_repo_factory()
        result_val = payload.get("result")
        if result_val is not None:
            result_json = json.dumps(result_val)
        else:
            result_json = payload.get("result_json", "{}")

        await mongo_repo.insert_inference_result(
            device_id,
            payload.get("deployment_id", ""),
            result_json,
        )

    async def _handle_event(self, payload: dict) -> None:
        """Saves deployment acknowledgment and script activation states to PostgreSQL.

        Args:
            payload: Event details.
        """
        event = payload.get("event")
        dep_id = payload.get("deployment_id")
        if not event or not dep_id:
            return

        async with self._sf() as s:
            repo = DeploymentRepository(s)
            dep = await repo.get(dep_id)
            if not dep:
                logger.warning(f"Unknown deployment_id: {dep_id}")
                return
            if event == "deploy_ack":
                await repo.mark_running(dep)
                logger.info(f"Deployment {dep_id} → running")
            elif event == "deploy_failed":
                await repo.mark_failed(dep, payload.get("error", "unknown"))
                logger.warning(f"Deployment {dep_id} → failed")

    async def _handle_status(self, device_id: str, payload: dict) -> None:
        """Saves device connectivity status changes (heartbeat, offline) to database registries.

        Args:
            device_id: Target device identifier.
            payload: Status payload.
        """
        status = payload.get("status", "offline")
        logger.info(f"Device '{device_id}' status update received: {status}")
        
        mongo_repo = self._mongo_repo_factory()
        await mongo_repo.upsert_device_state(device_id, {
            "status": status
        })
        
        try:
            from shared.proto_gen import device_pb2, device_pb2_grpc
            from app.config import get_settings
            import grpc
            s_cfg = get_settings()
            target_grpc = getattr(s_cfg, "device_service_grpc", s_cfg.ai_service_grpc)
            async with grpc.aio.insecure_channel(target_grpc) as channel:
                stub = device_pb2_grpc.DeviceServiceStub(channel)
                await stub.UpdateDeviceStatus(
                    device_pb2.UpdateDeviceStatusRequest(id=device_id, status=status)
                )
        except Exception as e:
            logger.error(f"Failed to update device status in registry for '{device_id}': {e}")
