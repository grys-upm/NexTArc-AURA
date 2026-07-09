"""Repository module wrapping MongoDB collections for device states and telemetry history."""
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.mongo import DEVICE_STATES_COL, INFERENCE_RESULTS_COL

class MonitoringRepository:
    """Provides MongoDB document access query handlers wrapping telemetry records."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initializes the MonitoringRepository.

        Args:
            db: Async Motor MongoDB database instance connection.
        """
        self._db = db

    async def upsert_device_state(self, device_id: str, state: dict) -> None:
        """Upserts a device's current state and appends entry to telemetry logs history.

        Args:
            device_id: Unique edge device ID.
            state: Telemetry resource metrics dictionary.
        """
        state["device_id"] = device_id
        state["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        
        await self._db[DEVICE_STATES_COL].update_one(
            {"device_id": device_id}, {"$set": state}, upsert=True
        )
        
        await self._db["telemetry_history"].insert_one({
            "device_id": device_id,
            "timestamp": state["last_seen_at"],
            "cpu_percent": state.get("cpu_percent", 0.0),
            "ram_percent": state.get("ram_percent", 0.0),
            "ram_used_mb": state.get("ram_used_mb", 0.0),
            "latency_ms": state.get("latency_ms", 0.0),
            "status": state.get("status", "online")
        })

    async def get_device_state(self, device_id: str) -> dict | None:
        """Retrieves current telemetry status document of a specific device.

        Args:
            device_id: Target device ID.

        Returns:
            Telemetry state dictionary or None if not found.
        """
        return await self._db[DEVICE_STATES_COL].find_one(
            {"device_id": device_id}, {"_id": 0}
        )

    async def list_device_states(self) -> list[dict]:
        """Lists current status telemetry for all active devices.

        Returns:
            List of telemetry state dictionaries.
        """
        cursor = self._db[DEVICE_STATES_COL].find({}, {"_id": 0})
        return await cursor.to_list(length=None)

    async def insert_inference_result(self, device_id: str, deployment_id: str, result_json: str) -> None:
        """Appends a new YOLO inference result log entry.

        Args:
            device_id: Source device ID.
            deployment_id: Deployment UUID.
            result_json: Raw inference output predictions JSON string.
        """
        await self._db[INFERENCE_RESULTS_COL].insert_one({
            "device_id": device_id,
            "deployment_id": deployment_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result_json": result_json,
        })

    async def get_inference_results(self, device_id: str, limit: int = 20) -> list[dict]:
        """Retrieves a historical sorted list of inference logs for a device.

        Args:
            device_id: Target device ID.
            limit: Maximum quantity of logs to retrieve.

        Returns:
            List of inference result dicts.
        """
        cursor = self._db[INFERENCE_RESULTS_COL].find(
            {"device_id": device_id}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=None)

    async def delete_device_data(self, device_id: str) -> None:
        """Wipes all state history, logs, and telemetry for a device.

        Args:
            device_id: Target device ID.
        """
        await self._db[DEVICE_STATES_COL].delete_one({"device_id": device_id})
        await self._db["telemetry_history"].delete_many({"device_id": device_id})
        await self._db[INFERENCE_RESULTS_COL].delete_many({"device_id": device_id})
