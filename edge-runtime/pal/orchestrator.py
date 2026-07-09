"""
PAL — Orchestrator
===================
Central coordinator of the edge agent. Manages two independent async
loops and maintains consistent device state across both.

Inference Loop
--------------
Runs every ``inference_interval_s`` seconds (default 0.1 s).

* Requires a model to be loaded (via OTA deploy). If no model is
  loaded, the tick is **skipped silently** (warning logged, nothing
  published).
* Captures a frame from the primary camera via the :class:`DeviceManager`
  (component ``camera_0``) and passes it as input to the inference backend.
* Stores the result in ``_last_inference`` for the telemetry loop.
* Publishes result + timestamp to ``device/{id}/inference``.
* Updates ``local_state.json``.

Telemetry Loop
--------------
Runs every ``telemetry_interval_s`` seconds (default 10 s).

* Collects system metrics (CPU, RAM, temperature via psutil).
* Reads all connected device states from :class:`DeviceManager`.
* Calls the user script ``run(raw_input)`` if one is loaded, passing
  the latest captured frame as ``raw_input``.
* Publishes the combined payload to ``device/{id}/telemetry``.
* Updates ``local_state.json``.

State Management
----------------
The orchestrator owns the single source of truth for deployment state.
The OTAHandler calls ``apply_deployment()`` after a successful download.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

# Setup logging for this module
logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """
    Returns the current UTC time formatted as an ISO 8601 string.

    :return: ISO 8601 formatted date-time string.
    :rtype: str
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Orchestrator:
    """
    Central coordinator of the edge agent.

    This class manages the inference and telemetry loops, tracks machine learning
    latencies, keeps coordinates from GPS sensors, and manages active deployment state.

    :ivar _comm: Communication client to publish messages.
    :type _comm: CommunicationClient
    :ivar _device_manager: Component device manager.
    :type _device_manager: DeviceManager
    :ivar _work_dir: Directory where state JSON is saved.
    :type _work_dir: Path
    :ivar _inference_interval: Time interval in seconds between inference ticks.
    :type _inference_interval: float
    :ivar _telemetry_interval: Time interval in seconds between telemetry ticks.
    :type _telemetry_interval: float
    :ivar _start_time: Monotonic startup timestamp.
    :type _start_time: float
    :ivar _primary_camera_id: Target camera ID to retrieve frames from.
    :type _primary_camera_id: str
    :ivar _coordinates: Local GPS coordinates (latitude, longitude).
    :type _coordinates: list[float] or None
    :ivar _active_deployment_id: ID of the currently active deployment.
    :type _active_deployment_id: str
    :ivar _active_model_id: ID of the currently active model.
    :type _active_model_id: str
    :ivar _active_script_id: ID of the currently active user script.
    :type _active_script_id: str
    :ivar _script_module: Dynamically loaded Python module from the user script.
    :type _script_module: types.ModuleType or None
    """

    def __init__(
        self,
        comm_client: Any,
        device_manager: Any,
        work_dir: Path,
        inference_interval_s: float = 0.1,
        telemetry_interval_s: float = 10.0,
        start_time: float | None = None,
        primary_camera_id: str = "camera_0",
        coordinates: list[float] | None = None,
    ) -> None:
        """
        Initializes the Orchestrator with components, directories, and intervals.

        :param comm_client: PAL communication client.
        :type comm_client: CommunicationClient
        :param device_manager: Hardware device manager.
        :type device_manager: DeviceManager
        :param work_dir: Directory to save state json files.
        :type work_dir: Path
        :param inference_interval_s: Time between inferences.
        :type inference_interval_s: float
        :param telemetry_interval_s: Time between telemetry reports.
        :type telemetry_interval_s: float
        :param start_time: Custom start time monotonic value.
        :type start_time: float or None
        :param primary_camera_id: Active camera component ID.
        :type primary_camera_id: str
        :param coordinates: Default coordinates.
        :type coordinates: list[float] or None
        """
        self._comm = comm_client
        self._device_manager = device_manager
        self._work_dir = work_dir
        self._inference_interval = inference_interval_s
        self._telemetry_interval = telemetry_interval_s
        self._start_time = start_time or time.monotonic()
        self._primary_camera_id = primary_camera_id
        self._coordinates = coordinates

        # ── Deployment state ──────────────────────────────────────────────
        self._active_deployment_id = ""
        self._active_model_id = ""
        self._active_script_id = ""
        self._script_module = None

        # ── Last inference result (shared between loops) ───────────────────
        self._inference_latencies = []
        self._last_frame = None
        self._last_inference = None
        self._last_inference_ts = None

        # ── Timestamps ────────────────────────────────────────────────────
        self._last_telemetry_ts = None

    # ── Public API ──────────────────────────────────────────────────────────

    def apply_deployment(self, state: dict) -> None:
        """
        Atomically updates the in-memory deployment state.

        Typically invoked by the OTAHandler once resources are verified.

        :param state: New deployment details (ids and loaded script module).
        :type state: dict
        """
        self._active_deployment_id = state.get("active_deployment_id", "")
        self._active_model_id = state.get("active_model_id", "")
        self._active_script_id = state.get("active_script_id", "")
        self._script_module = state.get("script_module")
        logger.info(
            f"Deployment applied: id={self._active_deployment_id} "
            f"model={self._active_model_id} script={self._active_script_id}"
        )

    async def run_inference_loop(self) -> None:
        """
        Runs the inference execution loop until cancelled.
        """
        logger.info(
            f"Inference loop started (interval={self._inference_interval}s)"
        )
        while True:
            try:
                # Execute a single tick pass
                await self._inference_tick()
            except asyncio.CancelledError:
                logger.info("Inference loop cancelled")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Inference tick error: {exc}")
            # Wait for next tick interval
            await asyncio.sleep(self._inference_interval)

    async def run_telemetry_loop(self) -> None:
        """
        Runs the telemetry publishing loop until cancelled.
        """
        logger.info(
            f"Telemetry loop started (interval={self._telemetry_interval}s)"
        )
        while True:
            try:
                # Execute a single tick pass
                await self._telemetry_tick()
            except asyncio.CancelledError:
                logger.info("Telemetry loop cancelled")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Telemetry tick error: {exc}")
            # Wait for next tick interval
            await asyncio.sleep(self._telemetry_interval)

    # ── Loop internals ────────────────────────────────────────────────────────

    async def _inference_tick(self) -> None:
        """
        Executes a single inference iteration: grabs a frame, runs model, and publishes result.
        """
        from aura_hw import execute_inference, get_hardware_info

        # Skip inference if no model is loaded inside the hardware layer
        hw = get_hardware_info()
        if not hw["model_loaded"]:
            logger.debug("Inference tick skipped — no model loaded")
            return

        ts = _utcnow_iso()

        # Capture frame using the designated primary camera in the thread pool executor (non-blocking)
        frame = await asyncio.get_event_loop().run_in_executor(
            None, self._capture_frame
        )
        self._last_frame = frame

        # Run inference via the user script or fallback directly to execute_inference
        t0 = time.perf_counter()
        if self._script_module is not None and hasattr(self._script_module, "run"):
            run_fn = getattr(self._script_module, "run")
            result = await asyncio.get_event_loop().run_in_executor(
                None, run_fn, frame
            )
        else:
            result = await asyncio.get_event_loop().run_in_executor(
                None, execute_inference, frame
            )
        # Calculate latency in milliseconds and log to list
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self._inference_latencies.append(latency_ms)
        # Cap latency history to the last 100 entries
        if len(self._inference_latencies) > 100:
            self._inference_latencies.pop(0)
            
        self._last_inference = result
        self._last_inference_ts = ts

        # Publish the inference payload through the communication client
        payload = {
            "ts": ts,
            "hardware_type": hw["hardware_type"],
            "model_loaded": True,
            "deployment_id": self._active_deployment_id,
            "result": _serialise(result),
        }
        await self._comm.publish_inference(payload)
        # Persist updated status details locally
        self._persist_state()

    async def _telemetry_tick(self) -> None:
        """
        Gathers system information, reads GPS, executes custom script, and publishes telemetry.
        """
        from aura_hw import get_hardware_info
        from aura_hw.loader import get_libraries_hash

        ts = _utcnow_iso()
        mem = psutil.virtual_memory()
        hw = get_hardware_info()

        # Calculate average model inference latency over the interval
        if self._inference_latencies:
            avg_latency = sum(self._inference_latencies) / len(self._inference_latencies)
            self._inference_latencies.clear()
        else:
            avg_latency = 0.0

        # Scan for active GPS components to fetch updated coordinates
        for dev_id in self._device_manager.list_components():
            try:
                dev = self._device_manager.get_device(dev_id)
                if dev.device_type == "gps":
                    coords = dev.measure()
                    if isinstance(coords, list) and len(coords) == 2:
                        self._coordinates = coords
                        break
            except Exception as e:
                logger.warning(f"Failed to read GPS coordinates from device '{dev_id}': {e}")

        # Construct the telemetry dictionary payload
        payload = {
            "ts": ts,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": mem.percent,
            "ram_used_mb": round(mem.used / 1024 / 1024, 1),
            "uptime_s": round(time.monotonic() - self._start_time, 1),
            "hardware_type": hw["hardware_type"],
            "model_loaded": hw["model_loaded"],
            "backend": hw["backend"],
            "active_deployment_id": self._active_deployment_id,
            "active_model_id": self._active_model_id,
            "active_script_id": self._active_script_id,
            "libraries_hash": get_libraries_hash(),
            "coordinates": self._coordinates,
            "latency_ms": round(avg_latency, 2),
        }

        # Include processor/GPU temperature measurements if available
        temps = _read_temperatures()
        if temps:
            payload["temperatures"] = temps

        # Append hardware information from peripheral classes
        payload["devices"] = self._device_manager.get_all_info()

        # Run custom user script logic in a thread
        script_output = await self._run_user_script()
        if script_output is not None:
            payload["script_output"] = _serialise(script_output)

        self._last_telemetry_ts = ts
        # Publish the telemetry payload
        await self._comm.publish_telemetry(payload)
        self._persist_state()
        logger.debug(f"Telemetry published at {ts}")

    async def _run_user_script(self) -> Any:
        """
        Invokes the user-defined python script module's run method inside an executor.

        :return: Script output structure or an error dict on failure.
        :rtype: Any
        """
        if self._script_module is None:
            return None
        run_fn = getattr(self._script_module, "run", None)
        if run_fn is None:
            logger.warning("User script has no run() function")
            return None
        raw_input = self._last_frame
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, run_fn, raw_input
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"User script error: {exc}")
            return {"error": str(exc)}

    def _capture_frame(self) -> Any:
        """
        Captures a single frame from the primary camera via DeviceManager.

        :return: Captured frame raw bytes or None if camera is missing or failed.
        :rtype: Any
        """
        try:
            camera = self._device_manager.get_device(self._primary_camera_id)
            return camera.capture_frame()
        except KeyError:
            logger.debug(
                f"Primary camera '{self._primary_camera_id}' not found in DeviceManager"
            )
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Frame capture error: {exc}")
            return None

    # ── State persistence ─────────────────────────────────────────────────────

    def _persist_state(self) -> None:
        """
        Saves current platform states and IDs to local_state.json.
        """
        from aura_hw import get_hardware_info

        hw = get_hardware_info()
        state = {
            "_comment": (
                "Auto-generated by AURA Edge Runtime. "
                "Do not edit manually — it is overwritten on every update."
            ),
            "device_status": "running",
            "active_deployment_id": self._active_deployment_id,
            "active_model_id": self._active_model_id,
            "active_script_id": self._active_script_id,
            "model_loaded": hw["model_loaded"],
            "hardware_type": hw["hardware_type"],
            "backend": hw["backend"],
            "last_inference_ts": self._last_inference_ts,
            "last_telemetry_ts": self._last_telemetry_ts,
            "uptime_s": round(time.monotonic() - self._start_time, 1),
            "components": self._device_manager.get_all_info(),
        }
        state_path = self._work_dir / "local_state.json"
        try:
            state_path.write_text(json.dumps(state, indent=2))
        except OSError as exc:
            logger.warning(f"Could not write local_state.json: {exc}")


# ── Module-level helpers ──────────────────────────────────────────────────────


def _serialise(value: Any) -> Any:
    """
    Serializes custom classes and numpy types into standard Python structures.

    :param value: Input values.
    :type value: Any
    :return: JSON-serializable types.
    :rtype: Any
    """
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, dict):
            return {k: _serialise(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_serialise(v) for v in value]
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
    except ImportError:
        pass
    return value


def _read_temperatures() -> dict[str, float]:
    """
    Fetches hardware thermal sensor details.

    :return: Mapping labels to temperature in Celsius.
    :rtype: dict[str, float]
    """
    try:
        sensors = psutil.sensors_temperatures()
        if not sensors:
            return {}
        result = {}
        for name, entries in sensors.items():
            for entry in entries:
                label = entry.label or name
                result[label] = round(entry.current, 1)
        return result
    except (AttributeError, Exception):  # noqa: BLE001
        return {}
