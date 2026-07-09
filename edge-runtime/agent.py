"""
AURA Edge Agent — Entrypoint.

Minimal entrypoint that wires together the PAL components:
- pal.comm_client: MQTT publish/subscribe
- pal.ota_handler: OTA deploy handler
- pal.orchestrator: inference + telemetry loops
- aura_hw.device_manager: connected device backends

Configuration priority:
1. Environment variables
2. config/device_config.yaml
3. Built-in defaults
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
import yaml


def _setup_logging(level_str: str) -> None:
    """
    Configures global system logging for the edge agent.

    :param level_str: Logging severity level name string.
    :type level_str: str
    """
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        stream=sys.stdout,
        level=level,
        format="%(asctime)s [edge-agent] %(levelname)s — %(message)s",
    )


_CONFIG_DIR = Path(__file__).parent / "config"
"""Path to the directory containing configuration files."""

_COMPONENTS_CONFIG_PATH = _CONFIG_DIR / "components_config.yaml"
"""Path to the active component drivers config schema yaml file."""


async def main() -> None:
    """
    Parses settings, initializes driver libraries, and runs client loops.

    Loads environment variables for MQTT connection parameters, working directories,
    intervals, and GPS coordinates. Saves active configuration to a YAML file,
    registers command handlers, starts the communication task and orchestrator loops
    using a TaskGroup, and ensures graceful teardown of connected peripherals on shutdown.
    """
    # Resolve all config values from environment variables or defaults
    device_id          = os.environ.get("AURA_DEVICE_ID",          "dev-device-001")
    mqtt_host          = os.environ.get("AURA_MQTT_HOST",          "localhost")
    mqtt_port          = int(os.environ.get("AURA_MQTT_PORT",      "1883"))
    reconnect_s        = int(os.environ.get("AURA_RECONNECT_S",    "5"))
    telemetry_interval = float(os.environ.get("AURA_TELEMETRY_INTERVAL", "10"))
    inference_interval = float(os.environ.get("AURA_INFERENCE_INTERVAL", "0.1"))
    work_dir           = Path(os.environ.get("AURA_WORK_DIR",      "/tmp/aura"))
    log_level          = os.environ.get("AURA_LOG_LEVEL",          "INFO")
    
    # Resolve primary camera ID from env vars or peripheral config lists
    primary_camera_id = os.environ.get("AURA_PRIMARY_CAMERA")
    if not primary_camera_id:
        peripherals_env = os.environ.get("AURA_PERIPHERALS")
        if peripherals_env:
            try:
                import json
                if peripherals_env.strip().startswith("["):
                    periphs = json.loads(peripherals_env)
                else:
                    periphs = [p.strip() for p in peripherals_env.split(",") if p.strip()]
                # Find the first peripheral matching 'camera'
                cam_ids = [p for p in periphs if "camera" in p.lower()]
                if cam_ids:
                    primary_camera_id = cam_ids[0]
            except Exception:
                pass
    if not primary_camera_id:
        primary_camera_id = "camera_0"
        
    coordinates_raw    = os.environ.get("AURA_COORDINATES",        "[-3.6294, 40.3897]")

    # Parse and validate default device GPS coordinates
    import json
    try:
        coordinates = json.loads(coordinates_raw) if isinstance(coordinates_raw, str) else coordinates_raw
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            coordinates = [-3.7038, 40.4168]
    except Exception:
        coordinates = [-3.7038, 40.4168]

    # Setup the global logger
    _setup_logging(log_level)
    logger = logging.getLogger(__name__)

    # Build active settings dictionary
    active_config = {
        "device_id": device_id,
        "mqtt_host": mqtt_host,
        "mqtt_port": mqtt_port,
        "mqtt_reconnect_interval_s": reconnect_s,
        "hardware_type": os.environ.get("AURA_HARDWARE_TYPE", "rpi"),
        "telemetry_interval_s": telemetry_interval,
        "inference_interval_s": inference_interval,
        "work_dir": str(work_dir),
        "log_level": log_level,
        "primary_camera_id": primary_camera_id,
        "coordinates": coordinates,
    }
    
    # Write the resolved config to device_config.yaml locally
    try:
        with open(_CONFIG_DIR / "device_config.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(active_config, f, default_flow_style=False)
            logger.info("Active configuration saved to device_config.yaml")
    except Exception as exc:
        logger.warning(f"Could not save active configuration to device_config.yaml: {exc}")

    # Register OS signal handlers for graceful shutdown
    import signal
    def handle_sigterm(*args):
        logger.info("Signal received — exiting gracefully")
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigterm)
    except ValueError:
        pass

    # Ensure the workspace directory exists
    work_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"AURA Edge Agent starting — device_id={device_id}")

    # Import PAL and backend manager modules
    from pal.comm_client import CommunicationClient
    from pal.ota_handler import OTAHandler
    from pal.orchestrator import Orchestrator
    from aura_hw.device_manager import DeviceManager

    start_time = time.monotonic()

    # Initialize and open device manager drivers
    device_manager = DeviceManager(_COMPONENTS_CONFIG_PATH)
    device_manager.open_all()
    logger.info(
        f"Device manager initialised: "
        f"components={device_manager.list_components()}"
    )

    # Instantiate the communication client
    comm = CommunicationClient(
        device_id=device_id,
        host=mqtt_host,
        port=mqtt_port,
        reconnect_interval_s=reconnect_s,
        db_path=work_dir / f"mqtt_buffer_{device_id}.db",
    )

    # Instantiate the central orchestrator
    orchestrator = Orchestrator(
        comm_client=comm,
        device_manager=device_manager,
        work_dir=work_dir,
        inference_interval_s=inference_interval,
        telemetry_interval_s=telemetry_interval,
        start_time=start_time,
        primary_camera_id=primary_camera_id,
        coordinates=coordinates,
    )

    # Instantiate the OTA handler
    ota = OTAHandler(
        work_dir=work_dir,
        on_event=comm.publish_event,
        on_deploy_success=orchestrator.apply_deployment,
        device_manager=device_manager,
    )

    # Register command message callbacks on the communication client
    comm.register_command_handler("deploy", ota.handle_deploy)
    comm.register_command_handler("update_libraries", ota.handle_update_libraries)

    # Run client, inference and telemetry loops concurrently using a TaskGroup
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(comm.run(),                    name="mqtt-loop")
            tg.create_task(orchestrator.run_inference_loop(), name="inference-loop")
            tg.create_task(orchestrator.run_telemetry_loop(), name="telemetry-loop")
    finally:
        # Tear down and release device peripherals
        logger.info("Shutting down — closing all devices")
        device_manager.close_all()

        # Publish final offline status message using a synchronous paho client
        logger.info("Publishing offline status to broker...")
        try:
            import paho.mqtt.client as mqtt
            client = mqtt.Client()
            client.connect(mqtt_host, mqtt_port, 60)
            client.publish(f"device/{device_id}/status", json.dumps({"status": "offline"}), retain=True)
            client.disconnect()
            logger.info("Offline status published successfully.")
        except Exception as e:
            logger.warning(f"Could not publish offline status on exit: {e}")

if __name__ == "__main__":
    asyncio.run(main())
