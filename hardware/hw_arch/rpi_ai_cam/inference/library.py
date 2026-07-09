"""
AURA RPi AI Camera Inference Client.
====================================
Handles offloaded neural network inference requests using physical Sony IMX500 AI Camera chip on Raspberry Pi 5.
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


class RPiAICamBackend:
    """
    RPi AI Camera (Sony IMX500) inference backend communicating with Host Hardware Daemon.
    """

    def __init__(self) -> None:
        """
        Initializes the client backend properties.
        """
        self._daemon_url = ""
        self._num_classes = 80
        self._class_names = []

    def load(self, model_path: str, class_names: list[str] = None) -> None:
        """
        Loads the compiled RPK model into the hardware daemon.

        :param model_path: Disk path to the compiled model (.rpk / .zip).
        :type model_path: str
        :param class_names: Optional class labels list.
        :type class_names: list[str] or None
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path does not exist: {model_path}")

        if class_names:
            self._class_names = class_names
            self._num_classes = len(class_names)
        else:
            self._class_names = []
            self._num_classes = 80

        # Resolve RPK path
        rpk_path = None
        
        import zipfile
        # 1. If it's a zip file (packerOut.zip), package it locally to network.rpk using imx500-package if available
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
            # Check magic bytes to see if it's a zip file even without extension
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

        gw_ip = _get_gateway_ip()
        self._daemon_url = f"http://{gw_ip}:8008"
        logger.info(f"Loading Sony IMX500 model on Host Daemon: {rpk_path} (URL: {self._daemon_url})")

        # Read the compiled .rpk file bytes
        with open(rpk_path, "rb") as f:
            rpk_bytes = f.read()

        # POST the model bytes to the daemon's /load endpoint
        req = urllib.request.Request(
            f"{self._daemon_url}/load",
            data=rpk_bytes,
            headers={"Content-Type": "application/octet-stream"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("status") != "success":
                    raise RuntimeError(f"Daemon failed to load model: {res.get('error')}")
                logger.info("Sony IMX500 model loaded successfully on Host Daemon.")
        except Exception as e:
            logger.error(f"Failed to communicate with Host Hardware Daemon to load model: {e}")
            raise RuntimeError(f"Failed to load model on Host Daemon: {e}")

    def infer(self, inputs: Any) -> dict[str, np.ndarray]:
        """
        Triggers onboard capture and inference on the physical AI camera.

        :param inputs: Dummy argument (onboard sensor handles capture directly).
        :type inputs: Any
        :return: Reconstructed predictions matching {"output0": boxes_array}.
        :rtype: dict
        """
        if not self._daemon_url:
            raise RuntimeError("Model is not loaded. Call load() first.")

        # POST the request to the daemon's /infer endpoint
        req = urllib.request.Request(
            f"{self._daemon_url}/infer",
            data=b"",  # No input image sent over the network (sensor-driven onboard inference)
            headers={"Content-Type": "application/octet-stream"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("status") != "success":
                    raise RuntimeError(f"Daemon inference failed: {res.get('error')}")
                outputs = res.get("detections", [])
        except Exception as e:
            logger.error(f"Failed to run inference on Host Hardware Daemon: {e}")
            return {"output0": np.zeros((1, 4 + self._num_classes, 0), dtype=np.float32)}

        # Reconstruct outputs to fit the YOLOv8 format (1, 4 + num_classes, num_detections)
        logger.debug(f"RPiAICamBackend.infer - Raw outputs: {outputs}")
        logger.debug(f"RPiAICamBackend.infer - num_classes={self._num_classes}, class_names={self._class_names}")

        if not outputs or len(outputs) < 3:
            return {"output0": np.zeros((1, 4 + self._num_classes, 0), dtype=np.float32)}

        boxes = np.array(outputs[0], dtype=np.float32)
        block_1 = np.array(outputs[1], dtype=np.float32)
        block_2 = np.array(outputs[2], dtype=np.float32)

        # Dynamically determine which block is scores and which is classes.
        # Confidence scores are always in range [0, 1].
        # Class IDs can be > 1.0 (e.g. 4.0, 3.0) if unquantized.
        if np.max(block_2) > 1.0:
            classes = block_2
            scores = block_1
        elif np.max(block_1) > 1.0:
            classes = block_1
            scores = block_2
        else:
            # Both are <= 1.0. The block with the larger maximum is the scores block
            # (since max class ID is 7/256 = 0.027, whereas scores go up to 1.0).
            if np.max(block_1) > np.max(block_2):
                scores = block_1
                classes = block_2
            else:
                scores = block_2
                classes = block_1

        if len(outputs) >= 4 and outputs[3] is not None and len(outputs[3]) > 0:
            num_detections = int(outputs[3][0])
        else:
            num_detections = boxes.shape[0]

        logger.debug(f"RPiAICamBackend.infer - num_detections={num_detections}, boxes shape={boxes.shape}, classes shape={classes.shape}, scores shape={scores.shape}")

        boxes = boxes[:num_detections]
        classes = classes[:num_detections]
        scores = scores[:num_detections]

        num_classes = self._num_classes
        mock_out = np.zeros((1, 4 + num_classes, num_detections), dtype=np.float32)

        for idx in range(num_detections):
            if idx >= boxes.shape[0] or idx >= classes.shape[0] or idx >= scores.shape[0]:
                break

            xmin, ymin, xmax, ymax = boxes[idx]
            score = scores[idx]
            
            # Support both direct integer class IDs and 1/256.0 normalized ones
            raw_class = classes[idx]
            if 0.0 < raw_class < 1.0:
                class_id = int(round(raw_class * 256.0))
            else:
                class_id = int(round(raw_class))

            w_box = xmax - xmin
            h_box = ymax - ymin
            cx = xmin + w_box / 2.0
            cy = ymin + h_box / 2.0

            mock_out[0, 0, idx] = cx
            mock_out[0, 1, idx] = cy
            mock_out[0, 2, idx] = w_box
            mock_out[0, 3, idx] = h_box
            if 0 <= class_id < num_classes:
                mock_out[0, 4 + class_id, idx] = score

        return {"output0": mock_out}

    def unload(self) -> None:
        """
        Instructs the daemon to unload the network.
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
            "hardware_type": "rpi_ai_cam",
            "accelerator": "Sony IMX500 AI Camera (via Host Daemon)",
            "sdk": "imx500-tools",
            "class_names": self._class_names
        }
