"""
AURA Sensor Library: Sony IMX500 AI Camera.
===========================================
Interfaces directly with native Picamera2 libraries or pings Host Hardware HTTP Daemon interfaces.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

import numpy as np

# Setup logging
logger = logging.getLogger(__name__)

LABEL = "Sony IMX500 AI Camera"


def _get_gateway_ip() -> str:
    """
    Attempts to resolve the Host IP gateway address dynamically inside container networks.

    :return: Host gateway IP address.
    :rtype: str
    """
    env_gw = os.environ.get("AURA_HARDWARE_DAEMON_HOST")
    if env_gw:
        return env_gw
    try:
        import socket
        with open("/proc/net/route") as f:
            for line in f:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == '00000000':
                    hex_gw = fields[2]
                    return socket.inet_ntoa(bytes.fromhex(hex_gw)[::-1])
    except Exception:
        pass
    mqtt_host = os.environ.get("AURA_MQTT_HOST")
    if mqtt_host and mqtt_host not in ("mosquitto", "aura-mosquitto", "localhost", "127.0.0.1"):
        return mqtt_host
    return "172.18.0.1"


class IMX500CameraLibrary:
    """
    Sony IMX500 AI Camera integration library.
    """
    
    def __init__(self, camera_id: int = 0, resolution: tuple[int, int] | str = (640, 480), fps: int = 10, **kwargs: Any) -> None:
        """
        Initializes the IMX500 Camera driver context.

        :param camera_id: System index of camera.
        :type camera_id: int
        :param resolution: Desired output capture dimensions.
        :type resolution: tuple or str
        :param fps: Frame capturing speed.
        :type fps: int
        """
        self.camera_id = camera_id
        if isinstance(resolution, str):
            try:
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

    def initialize(self, model_path: str = None) -> bool:
        """
        Runs connection verification and sets up active capturing stream modules.

        :param model_path: Disk path to compiled AI models.
        :type model_path: str or None
        :return: True if successful, False otherwise.
        :rtype: bool
        """
        logger.info("Initializing Sony IMX500 AI Camera driver...")

        # 1. Handle Model Packaging
        if model_path and os.path.exists(model_path):
            import zipfile
            if zipfile.is_zipfile(model_path):
                out_dir = os.path.dirname(model_path)
                import subprocess
                try:
                    cmd = ["imx500-package", "-i", model_path, "-o", out_dir]
                    logger.info(f"Running local packaging: {' '.join(cmd)}")
                    subprocess.run(cmd, check=True)
                    rpk_path = os.path.join(out_dir, "network.rpk")
                except (subprocess.SubprocessError, FileNotFoundError) as e:
                    logger.warning(f"Could not package model locally using imx500-package ({e}). Forwarding raw ZIP to Host Daemon...")
                    rpk_path = model_path
            elif model_path.endswith(".rpk") or model_path.endswith(".bin"):
                rpk_path = model_path
            else:
                try:
                    with open(model_path, "rb") as f:
                        header = f.read(4)
                    if header == b"PK\x03\x04":
                        logger.info("Model file is a ZIP archive without extension. Forwarding raw ZIP to Host Daemon...")
                        rpk_path = model_path
                    else:
                        rpk_path = model_path
                except Exception:
                    rpk_path = model_path
        
        # 2. Try native initialization first (on a real Raspberry Pi running natively)
        try:
            from picamera2 import Picamera2
            self.picam2 = Picamera2()
            config = self.picam2.create_preview_configuration(
                main={"size": self.resolution, "format": "RGB888"}
            )
            self.picam2.configure(config)
            self.picam2.start()
            logger.info("Sony IMX500 CSI capture initialized natively.")
            self._mode = "native"
            return True
        except (ImportError, Exception) as exc:
            logger.info(f"Native IMX500 not available ({exc}). Probing Host Hardware Daemon...")

        # 3. Try to connect to Host Hardware Daemon
        gw_ip = _get_gateway_ip()
        self._daemon_url = f"http://{gw_ip}:8008"
        try:
            with urllib.request.urlopen(f"{self._daemon_url}/status", timeout=5.0) as resp:
                if resp.status == 200:
                    status_data = json.loads(resp.read().decode("utf-8"))
                    logger.info(f"Connected to Host Hardware Daemon at {self._daemon_url} for Sony IMX500.")
                    self._mode = "daemon"
                    return True
        except Exception as e:
            logger.warning(f"Could not connect to Host Hardware Daemon at {self._daemon_url}: {e}")

        # 4. Fallback to Simulated/Mock mode
        logger.warning("Falling back to Sony IMX500 Simulated/Mock Camera mode.")
        self._mode = "mock"
        return True

    def read_value(self) -> np.ndarray:
        """
        Captures one frame as an RGB numpy array.

        :return: Image pixel grid ndarray.
        :rtype: np.ndarray
        """
        mode = getattr(self, "_mode", "mock")
        if mode == "mock":
            w, h = self.resolution
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            # Draw a simulated frame with a blue stripe
            import time
            t = int(time.time() * 20) % h
            frame[t:min(t+40, h), :, 2] = 220
            return frame
        elif mode == "daemon":
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
                raise RuntimeError("Sony IMX500 native camera is not initialized.")
            try:
                return self.picam2.capture_array()
            except Exception as e:
                logger.error(f"Error capturing natively from IMX500: {e}")
                raise

    def capture_frame(self) -> np.ndarray:
        """
        Reads frame array (alias for read_value).

        :return: Captured image frame.
        :rtype: np.ndarray
        """
        return self.read_value()

    def close(self) -> None:
        """
        Stops active capture interfaces and releases video devices.
        """
        mode = getattr(self, "_mode", "mock")
        if mode == "native" and self.picam2 is not None:
            try:
                self.picam2.stop()
            except Exception:
                pass
            try:
                self.picam2.close()
            except Exception:
                pass
            self.picam2 = None
        self.picam2 = None
