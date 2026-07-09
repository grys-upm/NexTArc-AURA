"""
AURA Sensor Library: RPi Camera Module 3
========================================
Integrates with physical Raspberry Pi Camera Module 3 using Picamera2 APIs or HTTP socket streams.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

# Setup logging
logger = logging.getLogger(__name__)

LABEL = "RPi Camera Module 3"


def _get_gateway_ip() -> str:
    """
    Attempts to resolve the Host IP gateway address dynamically inside container networks.

    :return: Host gateway IP address.
    :rtype: str
    """
    import os
    import socket
    # 1. Environment variable override
    env_gw = os.environ.get("AURA_HARDWARE_DAEMON_HOST")
    if env_gw:
        return env_gw
        
    # 2. Dynamically resolve gateway IP by reading /proc/net/route
    try:
        with open("/proc/net/route") as f:
            for line in f:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == '00000000':
                    hex_gw = fields[2]
                    return socket.inet_ntoa(bytes.fromhex(hex_gw)[::-1])
    except Exception:
        pass
        
    # 3. Fallback to AURA_MQTT_HOST if not standard container names
    mqtt_host = os.environ.get("AURA_MQTT_HOST")
    if mqtt_host and mqtt_host not in ("mosquitto", "aura-mosquitto", "localhost", "127.0.0.1"):
        return mqtt_host
        
    # 4. Standard default gateway fallback
    return "172.18.0.1"


class RPiCameraLibrary:
    """
    Raspberry Pi Camera Module 3 integration library.
    """

    def __init__(self, camera_id: int = 0, resolution: tuple[int, int] | str = (640, 480), fps: int = 10, **kwargs: Any) -> None:
        """
        Initializes the Camera Module 3 driver context.

        :param camera_id: System index of camera.
        :type camera_id: int
        :param resolution: Desired output capture dimensions.
        :type resolution: tuple or str
        :param fps: Frame capturing speed.
        :type fps: int
        """
        self.camera_id = camera_id
        # Support either string resolution "[640, 480]" or list/tuple
        if isinstance(resolution, str):
            try:
                import json
                self.resolution = tuple(json.loads(resolution))
            except Exception:
                self.resolution = (640, 480)
        elif isinstance(resolution, (list, tuple)):
            self.resolution = tuple(resolution)
        else:
            self.resolution = (640, 480)
            
        self.fps = int(fps)
        self.picam2 = None
        self._mode = "mock"
        self._daemon_url = ""

    def initialize(self) -> bool:
        """
        Initialize and configure the Picamera2 camera.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        logger.info("Initializing Picamera2 (RPi Camera Module 3)...")
        # 1. Try native initialization first
        try:
            from picamera2 import Picamera2
            self.picam2 = Picamera2()
            
            # Configure to output raw RGB frames at configured resolution
            config = self.picam2.create_preview_configuration(
                main={"size": self.resolution, "format": "RGB888"}
            )
            self.picam2.configure(config)
            self.picam2.start()
            logger.info("Picamera2 started successfully natively.")
            self._mode = "native"
            return True
        except (ImportError, Exception) as exc:
            logger.info(f"Native picamera2 not available ({exc}). Probing Host Hardware Daemon...")

        # 2. Try to connect to Host Hardware Daemon
        gw_ip = _get_gateway_ip()
        self._daemon_url = f"http://{gw_ip}:8008"
        
        import urllib.request
        import json
        try:
            with urllib.request.urlopen(f"{self._daemon_url}/status", timeout=5.0) as resp:
                if resp.status == 200:
                    status_data = json.loads(resp.read().decode("utf-8"))
                    logger.info(f"Connected to Host Hardware Daemon at {self._daemon_url} (Camera type: {status_data.get('camera_type')})")
                    self._mode = "daemon"
                    return True
        except Exception as e:
            logger.warning(f"Could not connect to Host Hardware Daemon at {self._daemon_url}: {e}")

        # 3. Fallback to Simulated/Mock Camera mode
        logger.warning("Falling back to local Simulated/Mock Camera mode.")
        self._mode = "mock"
        return True

    def read_value(self) -> np.ndarray:
        """
        Capture an RGB image frame from the camera.

        :return: Captured image pixel grid array.
        :rtype: np.ndarray
        """
        mode = getattr(self, "_mode", "mock")
        if mode == "mock":
            import time
            w, h = self.resolution
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            # Create a simple dynamic pattern (moving colored rectangles)
            t = int(time.time() * 20) % h
            frame[t:min(t+40, h), :, 0] = 200 # Red channel animation
            frame[:, (t*2)%w:min((t*2)%w+40, w), 1] = 180 # Green channel animation
            return frame

        elif mode == "daemon":
            import urllib.request
            try:
                with urllib.request.urlopen(f"{self._daemon_url}/capture", timeout=5.0) as resp:
                    raw_data = resp.read()
                    w, h = self.resolution
                    frame = np.frombuffer(raw_data, dtype=np.uint8).reshape((h, w, 3))
                    return frame
            except Exception as e:
                logger.error(f"Error reading frame from Host Hardware Daemon: {e}")
                w, h = self.resolution
                return np.zeros((h, w, 3), dtype=np.uint8)

        else: # native mode
            if self.picam2 is None:
                raise RuntimeError("RPi Camera Module 3 is not initialized natively.")
            try:
                # Capture frame natively as an RGB numpy array
                return self.picam2.capture_array()
            except Exception as e:
                logger.error(f"Error capturing frame from native Picamera2: {e}")
                raise

    def capture_frame(self) -> np.ndarray:
        """
        Reads frame array (alias for read_value).

        :return: Image frame array data.
        :rtype: np.ndarray
        """
        return self.read_value()

    def close(self) -> None:
        """
        Stop and release camera resources.
        """
        mode = getattr(self, "_mode", "mock")
        if mode == "native" and self.picam2 is not None:
            try:
                self.picam2.stop()
                logger.info("Picamera2 stopped successfully.")
            except Exception as e:
                logger.warning(f"Error stopping Picamera2: {e}")
            try:
                self.picam2.close()
                logger.info("Picamera2 closed successfully.")
            except Exception as e:
                logger.warning(f"Error closing Picamera2: {e}")
            self.picam2 = None
        elif mode == "daemon":
            logger.info("Disconnected from Host Hardware Daemon.")
        self.picam2 = None
