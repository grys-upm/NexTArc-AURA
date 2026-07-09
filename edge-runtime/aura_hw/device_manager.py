"""
AURA Device Manager
=====================
Reads ``components_config.yaml``, instantiates the correct device
backend for each enabled component, and manages their lifecycle.

All device backends are loaded dynamically from the ``hardware/``
directory, which is populated via OTA when the device connects to
the AURA platform.

Usage
-----
::

    from pathlib import Path
    from aura_hw.device_manager import DeviceManager

    dm = DeviceManager(Path("config/components_config.yaml"))
    dm.open_all()

    frame = dm.get_device("camera_0").capture_frame()
    reading = dm.get_device("env_sensor_0").measure()

    dm.close_all()
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from aura_hw.backends.devices.base import DeviceBackend

logger = logging.getLogger(__name__)


# ── Dynamic factories ────────────────────────────────────────────────────────
# All backends are loaded dynamically from hardware/<category>/<driver>/library.py.

# Define factory functions to lazily import and instantiate the appropriate device backends
# based on categories (camera, sensor, actuator, etc.) to keep initial import times lightweight.

def _make_camera(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create the Camera backend instance using the specified driver.
    from aura_hw.backends.devices.camera.general import GeneralCameraBackend
    return GeneralCameraBackend(cid, driver)

def _make_sensor(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a generic Sensor backend instance.
    from aura_hw.backends.devices.sensor.general import GeneralSensorBackend
    return GeneralSensorBackend(cid, "sensor", driver)

def _make_temperature(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a Temperature sensor backend instance.
    from aura_hw.backends.devices.sensor.general import GeneralSensorBackend
    return GeneralSensorBackend(cid, "temperature", driver)

def _make_distance(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a Distance sensor backend instance.
    from aura_hw.backends.devices.sensor.general import GeneralSensorBackend
    return GeneralSensorBackend(cid, "distance", driver)

def _make_imu(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create an IMU sensor backend instance.
    from aura_hw.backends.devices.sensor.general import GeneralSensorBackend
    return GeneralSensorBackend(cid, "imu", driver)

def _make_led(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create an LED actuator backend instance.
    from aura_hw.backends.devices.actuator.general import GeneralActuatorBackend
    return GeneralActuatorBackend(cid, "led", driver)

def _make_buzzer(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a Buzzer actuator backend instance.
    from aura_hw.backends.devices.actuator.general import GeneralActuatorBackend
    return GeneralActuatorBackend(cid, "buzzer", driver)

def _make_servo(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a Servo actuator backend instance.
    from aura_hw.backends.devices.actuator.general import GeneralActuatorBackend
    return GeneralActuatorBackend(cid, "servo", driver)

def _make_relay(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a Relay actuator backend instance.
    from aura_hw.backends.devices.actuator.general import GeneralActuatorBackend
    return GeneralActuatorBackend(cid, "relay", driver)

def _make_gps(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a GPS sensor backend instance.
    from aura_hw.backends.devices.sensor.general import GeneralSensorBackend
    return GeneralSensorBackend(cid, "gps", driver)

def _make_template(cid: str, driver: str) -> DeviceBackend:
    # Lazily import and create a generic template backend instance for uncategorized devices.
    from aura_hw.backends.devices.other.general import GeneralOtherBackend
    return GeneralOtherBackend(cid, "template", driver)


# Maps device type strings from config to their respective backend factory functions.
_TYPE_FACTORIES: dict[str, callable] = {
    "camera": _make_camera,
    "sensor": _make_sensor,
    "temperature": _make_temperature,
    "distance": _make_distance,
    "imu": _make_imu,
    "led": _make_led,
    "buzzer": _make_buzzer,
    "servo": _make_servo,
    "relay": _make_relay,
    "gps": _make_gps,
    "template": _make_template,
}


class DeviceManager:
    """Lifecycle manager for all connected device backends.

    Reads ``components_config.yaml``, instantiates one backend per
    enabled component, and exposes a keyed-access API.

    Args:
        config_path (Path): Absolute path to ``components_config.yaml``.
    """

    def __init__(self, config_path: Path) -> None:
        # Initialize internal structures and trigger configuration loading.
        self._config_path = config_path
        self._devices: dict[str, DeviceBackend] = {}
        self._component_params: dict[str, dict] = {}
        self._load_config()

    # ── Public API ────────────────────────────────────────────────────────────

    def open_all(self) -> None:
        """Open all enabled device backends.

        Skips components whose drivers are not registered or that fail
        to open (logs an error but does not raise).
        """
        # Step through each registered device backend and open/initialize it using its parameters.
        for component_id, backend in self._devices.items():
            params = self._component_params.get(component_id, {})
            try:
                backend.open(params)
                logger.info(
                    f"[DeviceManager] Opened: {component_id} "
                    f"({backend.device_type}/{backend.driver})"
                )
            except Exception as exc:  # noqa: BLE001
                # Log failures instead of raising to allow other devices to continue starting up.
                logger.error(
                    f"[DeviceManager] Failed to open {component_id}: {exc}"
                )

    def close_all(self) -> None:
        """Close all open device backends in reverse instantiation order."""
        # Close all active backends in reverse order to ensure clean shutdowns.
        for component_id, backend in reversed(list(self._devices.items())):
            try:
                backend.close()
                logger.info(f"[DeviceManager] Closed: {component_id}")
            except Exception as exc:  # noqa: BLE001
                # Log warnings if closure fails so that teardown continues for other devices.
                logger.warning(
                    f"[DeviceManager] Error closing {component_id}: {exc}"
                )

    def get_device(self, component_id: str) -> DeviceBackend:
        """Return the backend for a specific component.

        Args:
            component_id: The ``id`` field from ``components_config.yaml``.

        Returns:
            The instantiated :class:`~aura_hw.backends.devices.base.DeviceBackend`.

        Raises:
            KeyError: If no enabled component with that ID exists.
        """
        # Retrieve a device backend reference by its unique component identifier.
        if component_id not in self._devices:
            available = list(self._devices.keys())
            raise KeyError(
                f"No enabled device with id '{component_id}'. "
                f"Available: {available}"
            )
        return self._devices[component_id]

    def get_all_info(self) -> dict[str, dict]:
        """Return ``info()`` for every managed device.

        Returns:
            Dict mapping ``component_id → info_dict``.
        """
        # Retrieve configuration/runtime information dictionary for all active device backends.
        result: dict[str, dict] = {}
        for component_id, backend in self._devices.items():
            try:
                result[component_id] = backend.info()
            except Exception as exc:  # noqa: BLE001
                # Capture information gathering errors directly in the result payload.
                result[component_id] = {"error": str(exc)}
        return result

    def list_components(self) -> list[str]:
        """Return the IDs of all managed (enabled) components."""
        # Return a list of all currently active component identifier strings.
        return list(self._devices.keys())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        """Parse the YAML config and instantiate backends for enabled components."""
        import os
        
        # Step 1: Read and parse the components YAML configuration file.
        try:
            with open(self._config_path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.warning(
                f"[DeviceManager] components_config.yaml not found at "
                f"{self._config_path} — no devices will be managed."
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[DeviceManager] Failed to read config: {exc}")
            return

        # Step 2: Parse AURA_PERIPHERALS environment variable filter if specified.
        # This allows active peripherals to be overridden/filtered at runtime via environment.
        peripherals_env = os.environ.get("AURA_PERIPHERALS")
        active_peripherals = None
        if peripherals_env:
            try:
                import json
                # Handle JSON array representation (e.g. '["camera_0", "led_0"]')
                if peripherals_env.strip().startswith("["):
                    active_peripherals = set(json.loads(peripherals_env))
                # Handle comma-separated list representation (e.g. 'camera_0,led_0')
                else:
                    active_peripherals = set(p.strip() for p in peripherals_env.split(",") if p.strip())
            except Exception as exc:
                logger.error(f"[DeviceManager] Failed to parse AURA_PERIPHERALS environment variable: {exc}")

        # Step 3: Iterate through components declared in the configuration.
        components = raw.get("components", [])
        for entry in components:
            component_id = entry.get("id", "<unnamed>")
            
            # Step 4: Determine if this component should be enabled.
            # If AURA_PERIPHERALS is defined, check if this component is listed there.
            # Otherwise, check the default 'enabled' boolean field from config (defaults to True).
            if active_peripherals is not None:
                is_enabled = component_id in active_peripherals
            else:
                is_enabled = entry.get("enabled", True)

            if not is_enabled:
                logger.debug(
                    f"[DeviceManager] Skipping disabled component: {component_id}"
                )
                continue
                
            # Extract component hardware type, driver name, and runtime parameters.
            device_type  = entry.get("type", "")
            driver       = entry.get("driver", "")
            params       = entry.get("params", {})

            # Step 5: Lookup the appropriate dynamic backend factory.
            type_factory = _TYPE_FACTORIES.get(device_type)
            if type_factory is None:
                logger.warning(
                    f"[DeviceManager] No backend factory for "
                    f"type='{device_type}' driver='{driver}' "
                    f"(component: {component_id}). Skipping."
                )
                continue

            # Step 6: Instantiate and register the device backend and parameters.
            try:
                backend = type_factory(component_id, driver)
                self._devices[component_id] = backend
                self._component_params[component_id] = params
                logger.debug(
                    f"[DeviceManager] Registered: {component_id} → "
                    f"{type(backend).__name__}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"[DeviceManager] Failed to instantiate backend for "
                    f"{component_id}: {exc}"
                )

