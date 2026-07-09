"""
Hardware auto-detection for the AURA edge runtime.

Probes the host system to determine which AI accelerator is available.
The result is cached after the first call so repeated imports don't
re-run the detection logic.

Detection order
---------------
1. ``AURA_HARDWARE_TYPE`` environment variable (override, highest priority)
2. ``hailortcli fw-control identify`` → ``hailo8`` / ``hailo8l``
3. ``libcamera-hello --list-cameras`` with *imx500* in output → ``rpi_ai_cam``
4. ``/proc/device-tree/model`` containing *raspberry* → ``rpi``
5. Fallback → ``unknown``

If the result is ``"unknown"``, :func:`~aura_hw.runtime.load_model` will
raise :exc:`RuntimeError`.  Set ``AURA_HARDWARE_TYPE`` to a supported
target to override auto-detection.
"""
import os
import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def detect_hardware() -> str:
    """Detect the available AI hardware on the current device.

    The result is cached after the first successful call via
    :func:`functools.lru_cache`.

    Returns:
        A hardware identifier string. One of:

        * ``"hailo8"``
        * ``"hailo8l"``
        * ``"rpi_ai_cam"``
        * ``"rpi"``
        * ``"unknown"``

    Note:
        Set the environment variable ``AURA_HARDWARE_TYPE`` to bypass
        auto-detection entirely::

            AURA_HARDWARE_TYPE=hailo8 python agent.py
    """
    # Step 1: Check for manual environment override.
    # If the AURA_HARDWARE_TYPE environment variable is set, bypass auto-detection and use it.
    override = os.environ.get("AURA_HARDWARE_TYPE")
    if override:
        return override.lower()

    # Step 2: Probe Host Hardware Daemon for hardware_type
    # This tries to query the host's hardware daemon over HTTP to determine the platform.
    try:
        import socket
        import urllib.request
        import json
        
        # Default gateway IP in Docker environments
        gw_ip = "172.18.0.1"
        try:
            # Read network routes to find the gateway IP address of the default route.
            with open("/proc/net/route") as f:
                for line in f:
                    fields = line.strip().split()
                    if len(fields) >= 3 and fields[1] == '00000000':
                        hex_gw = fields[2]
                        # Convert the hex representation of the gateway IP to a dotted-decimal string.
                        gw_ip = socket.inet_ntoa(bytes.fromhex(hex_gw)[::-1])
                        break
        except Exception:
            pass
            
        # If AURA_MQTT_HOST is set to an external host, use it as the gateway/daemon IP.
        mqtt_host = os.environ.get("AURA_MQTT_HOST")
        if mqtt_host and mqtt_host not in ("mosquitto", "aura-mosquitto", "localhost", "127.0.0.1"):
            gw_ip = mqtt_host
            
        # Call the status endpoint of the daemon running on the gateway IP.
        daemon_url = f"http://{gw_ip}:8008"
        with urllib.request.urlopen(f"{daemon_url}/status", timeout=5.0) as resp:
            if resp.status == 200:
                # Parse the JSON response and return the detected hardware type if present.
                status_data = json.loads(resp.read().decode("utf-8"))
                detected_hw = status_data.get("hardware_type")
                if detected_hw:
                    return detected_hw
    except Exception:
        pass

    # Step 3: Hailo PCIe accelerator (local fallback if running on host/standalone)
    # Attempt to query local Hailo hardware status using hailortcli.
    try:
        result = subprocess.run(
            ["hailortcli", "fw-control", "identify"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            # Distinguish between Hailo-8 and Hailo-8L based on command output.
            return "hailo8l" if "hailo8l" in result.stdout.lower() else "hailo8"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Step 4: Raspberry Pi AI Camera (Sony IMX500)
    # Check if the Raspberry Pi AI camera module is connected using libcamera-hello.
    try:
        result = subprocess.run(
            ["libcamera-hello", "--list-cameras"],
            capture_output=True, text=True, timeout=5,
        )
        # If 'imx500' is listed in the output cameras, we assume it is the Raspberry Pi AI camera.
        if "imx500" in result.stdout.lower():
            return "rpi_ai_cam"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Step 5: Generic Raspberry Pi
    # If not specifically an AI camera or Hailo, check the system device tree model.
    if os.path.exists("/proc/device-tree/model"):
        with open("/proc/device-tree/model") as f:
            if "raspberry" in f.read().lower():
                return "rpi"

    # Step 6: Fallback default
    # If no known hardware was detected, fallback to unknown.
    return "unknown"
