#!/usr/bin/env python3
"""
AURA Hardware Daemon.

Exposes Raspberry Pi Camera Module 3 and Hailo-8/8L hardware accelerators
over a lightweight local HTTP API.
Allows containerized edge agents to interact with native hardware without
complex device mounts or privileged Docker flags.

API Endpoints:
- GET /capture: Returns the latest captured frame as raw image bytes.
- GET /status: Returns JSON status of the daemon.
- POST /load: Accepts raw HEF bytes and initializes Hailo context.
- POST /infer: Runs inference on the loaded Hailo model using raw RGB888 bytes.
- POST /unload: Releases the Hailo context and cleans up temporary HEFs.
"""
import io
import json
import logging
import os
import sys
import time
import urllib.parse
import threading
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from daemon.shared import logger, HARDWARE_TYPE, CAMERA_ENABLED, HAS_PILLOW, _make_json_serializable
from daemon import camera_manager, hailo_manager, imx500_manager

PICAM_AVAIL = False
"""Boolean indicating if the native `picamera2` library can be imported."""
try:
    from picamera2 import Picamera2
    PICAM_AVAIL = True
except ImportError:
    pass

HAILO_AVAIL = False
"""Boolean indicating if the native `picamera2.devices.Hailo` class can be imported."""
try:
    from picamera2.devices import Hailo
    HAILO_AVAIL = True
except ImportError:
    pass

IMX500_AVAIL = False
"""Boolean indicating if the native `picamera2.devices.IMX500` class can be imported."""
try:
    from picamera2.devices import IMX500
    IMX500_AVAIL = True
except ImportError:
    pass


class HardwareHTTPHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler routing edge device camera and hardware compiler operations.

    Exposes API endpoints to capture frames, query status, and orchestrate
    deep learning model context loads and inferences.
    """
    
    def log_message(self, format: str, *args: Any) -> None:
        """
        Overrides the default request logging output.

        Suppresses HTTP transaction logs to keep the console clean during rapid,
        continuous frame captures.

        :param format: Log format string.
        :type format: str
        :param args: Formatting parameters.
        :type args: Any
        """
        pass

    def do_GET(self) -> None:
        """
        Handles incoming HTTP GET routes: `/capture` and `/status`.
        """
        # Route: GET /capture - returns the most recent frame captured by camera_manager
        if self.path == "/capture":
            raw_data = camera_manager.capture_raw()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(raw_data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(raw_data)
        # Route: GET /status - returns system capability JSON response
        elif self.path == "/status":
            status = {
                "status": "online",
                "hardware_type": HARDWARE_TYPE,
                "camera_type": "physical" if (PICAM_AVAIL and CAMERA_ENABLED) else "simulated",
                "picamera_available": PICAM_AVAIL,
                "camera_enabled": CAMERA_ENABLED,
                "hailo_available": HAILO_AVAIL,
                "imx500_available": IMX500_AVAIL,
                "pillow_available": HAS_PILLOW
            }
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            # Fallback 404 response
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        """
        Handles incoming HTTP POST routes: `/load`, `/infer`, and `/unload`.
        """
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        # Read the request body payload
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b""
        
        # Route: POST /load - loads neural network models dynamically (RPK for IMX500, HEF for Hailo)
        if path == "/load":
            if HARDWARE_TYPE == "rpi_ai_cam":
                res = imx500_manager.load(post_data)
            else:
                res = hailo_manager.load(post_data)
            body = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            
        # Route: POST /infer - runs model inference on target hardware accelerator
        elif path == "/infer":
            if HARDWARE_TYPE == "rpi_ai_cam":
                res = imx500_manager.infer()
            else:
                params = urllib.parse.parse_qs(parsed_url.query)
                w = int(params.get('w', [640])[0])
                h = int(params.get('h', [480])[0])
                res = hailo_manager.infer(post_data, w, h)
                
            # Serialize the output arrays to ensure JSON format compatibility
            res = _make_json_serializable(res)
            body = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            
        # Route: POST /unload - releases device model contexts and removes temp files
        elif path == "/unload":
            if HARDWARE_TYPE == "rpi_ai_cam":
                imx500_manager.unload()
            else:
                hailo_manager.unload()
            body = json.dumps({"status": "success"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            
        else:
            # Fallback 404 response
            self.send_response(404)
            self.end_headers()


def main() -> None:
    """
    Bootstraps the camera manager, configures loggers, handles signals, and starts the HTTP server.
    """
    import signal
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    port = 8008
    # Start the camera capture manager loop
    camera_manager.start()
    
    # Initialize HTTPServer
    server = HTTPServer(("0.0.0.0", port), HardwareHTTPHandler)
    logger.info(f"AURA Hardware Daemon listening on http://0.0.0.0:{port}")
    
    # Graceful shutdown helper callback
    def shutdown_handler(signum, frame) -> None:
        logger.info("Shutdown signal received. Stopping daemon...")
        camera_manager.stop()
        hailo_manager.unload()
        imx500_manager.unload()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    try:
        # Run server loop infinitely
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # Ensure cleanup tasks run on exit
        camera_manager.stop()
        hailo_manager.unload()


if __name__ == "__main__":
    main()
