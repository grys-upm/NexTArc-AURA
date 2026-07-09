"""
AURA Hailo-8L Inference Client.
===============================
Handles neural network inference on Host Daemon containing physical Hailo-8L NPU hardware.
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


def _get_gateway_ip() -> str:
    """
    Attempts to resolve the Host IP gateway address dynamically inside container networks.

    :return: Host gateway IP address.
    :rtype: str
    """
    # 1. Environment variable override
    env_gw = os.environ.get("AURA_HARDWARE_DAEMON_HOST")
    if env_gw:
        return env_gw
        
    # 2. Dynamically resolve gateway IP by reading /proc/net/route
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
        
    # 3. Fallback to AURA_MQTT_HOST if not standard container names
    mqtt_host = os.environ.get("AURA_MQTT_HOST")
    if mqtt_host and mqtt_host not in ("mosquitto", "aura-mosquitto", "localhost", "127.0.0.1"):
        return mqtt_host
        
    # 4. Standard default gateway fallback
    return "172.18.0.1"


class Hailo8LBackend:
    """
    Hailo-8L inference backend communicating with the Host Hardware Daemon.
    """

    def __init__(self) -> None:
        """
        Initializes the client backend properties.
        """
        self._daemon_url = ""
        self._num_classes = 80
        self._class_names = []
        self._input_height = 640
        self._input_width = 640

    def load(self, model_path: str, class_names: list[str] = None) -> None:
        """
        Requests the host hardware daemon to load model HEF bytes.

        :param model_path: Disk path to the compiled model (.hef).
        :type model_path: str
        :param class_names: Optional labels mapping classes.
        :type class_names: list[str] or None
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path does not exist: {model_path}")

        if class_names:
            self._class_names = class_names
        else:
            self._class_names = []

        gw_ip = _get_gateway_ip()
        self._daemon_url = f"http://{gw_ip}:8008"
        logger.info(f"Loading Hailo HEF model on Host Daemon: {model_path} (URL: {self._daemon_url})")

        # Read the compiled .hef file bytes
        with open(model_path, "rb") as f:
            hef_bytes = f.read()

        # POST the model bytes to the daemon's /load endpoint
        req = urllib.request.Request(
            f"{self._daemon_url}/load",
            data=hef_bytes,
            headers={"Content-Type": "application/octet-stream"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("status") != "success":
                    raise RuntimeError(f"Daemon failed to load model: {res.get('error')}")
                
                input_shape = res.get("input_shape")
                if input_shape and len(input_shape) >= 2:
                    self._input_height = int(input_shape[0])
                    self._input_width = int(input_shape[1])
                    
                logger.info(f"Hailo HEF model loaded successfully on Host Daemon (Input dimensions: {self._input_width}x{self._input_height}).")
        except Exception as e:
            logger.error(f"Failed to communicate with Host Hardware Daemon to load model: {e}")
            raise RuntimeError(f"Failed to load model on Host Daemon: {e}")

    def infer(self, inputs: Any) -> dict[str, np.ndarray]:
        """
        Transmits raw image frames to the host daemon and reconstructs YOLOv8 outputs.

        :param inputs: Input image ndarray of format HWC or NCHW.
        :type inputs: Any
        :return: Decoded predictions matching {"output0": boxes_array}.
        :rtype: dict
        """
        if not self._daemon_url:
            raise RuntimeError("Model is not loaded. Call load() first.")

        # Convert input to raw RGB888 HWC image
        if isinstance(inputs, np.ndarray):
            if len(inputs.shape) == 4:
                # NCHW -> HWC
                img = inputs[0]
                img = np.transpose(img, (1, 2, 0))
                # Denormalize if float
                if img.dtype != np.uint8:
                    img = (img * 255.0).astype(np.uint8)
            else:
                img = inputs
                if img.dtype != np.uint8:
                    img = (img * 255.0).astype(np.uint8)
        else:
            raise ValueError("Unsupported input format for HailoBackend: inputs must be np.ndarray")

        # Resize image to model expected shape client-side to optimize network payload
        import cv2
        if img.shape[0] != self._input_height or img.shape[1] != self._input_width:
            img = cv2.resize(img, (self._input_width, self._input_height))

        h, w, c = img.shape
        img_bytes = img.tobytes()

        # POST the raw RGB bytes to the daemon's /infer endpoint
        req = urllib.request.Request(
            f"{self._daemon_url}/infer?w={w}&h={h}",
            data=img_bytes,
            headers={"Content-Type": "application/octet-stream"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("status") != "success":
                    raise RuntimeError(f"Daemon inference failed: {res.get('error')}")
                hailo_output = res.get("detections", [])
        except Exception as e:
            logger.error(f"Failed to run inference on Host Hardware Daemon: {e}")
            return {"output0": np.zeros((1, 4 + self._num_classes, 0), dtype=np.float32)}

        # Reconstruct outputs to fit the YOLOv8 format (1, 4 + num_classes, num_detections)
        num_classes = len(hailo_output) if hailo_output else self._num_classes
        self._num_classes = num_classes
        num_detections = sum(len(dets) for dets in hailo_output)

        mock_out = np.zeros((1, 4 + num_classes, num_detections), dtype=np.float32)
        idx = 0
        for class_id, detections in enumerate(hailo_output):
            for detection in detections:
                if len(detection) < 5:
                    continue
                y0, x0, y1, x1 = detection[:4]
                score = detection[4]

                # Convert to center cx, cy, w_box, h_box in pixel coordinates
                w_box = (x1 - x0) * w
                h_box = (y1 - y0) * h
                cx = (x0 + (x1 - x0) / 2.0) * w
                cy = (y0 + (y1 - y0) / 2.0) * h

                mock_out[0, 0, idx] = cx
                mock_out[0, 1, idx] = cy
                mock_out[0, 2, idx] = w_box
                mock_out[0, 3, idx] = h_box
                mock_out[0, 4 + class_id, idx] = score
                idx += 1

        return {"output0": mock_out}

    def unload(self) -> None:
        """
        Signals the host daemon to release the allocated Hailo device context.
        """
        if self._daemon_url:
            req = urllib.request.Request(f"{self._daemon_url}/unload", method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    pass
            except Exception as e:
                logger.warning(f"Failed to unload model on Host Hardware Daemon: {e}")
            self._daemon_url = ""

    def device_info(self) -> dict[str, Any]:
        """
        Collects active SDK and hardware descriptor details.

        :return: Device metrics dictionary.
        :rtype: dict
        """
        return {
            "hardware_type": "hailo8l",
            "accelerator": "Hailo-8L NPU (via Host Daemon)",
            "sdk": "hailort",
            "class_names": self._class_names
        }
