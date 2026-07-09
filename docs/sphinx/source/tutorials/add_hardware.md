# How to Add New Hardware to the AURA Platform

The AURA Platform is designed with a plug-and-play architecture for custom hardware integration. You can add new target platforms in two ways:
1. **Hardware Architectures (`hardware/hw_arch`)**: Define how to compile and how to inference generic `.pt` model files into hardware-specific binary targets.
2. **Peripheral Drivers (`hardware/sensors`, `hardware/actuators`, `hardware/others`)**: Define how to control and fetch metrics from connected sensors or write signals to actuators.

---

## 1. Adding a Hardware Architecture Compiler

Model compilation is scanned dynamically by the `mlops-service` from the subdirectories inside `hardware/hw_arch`.

### Step 1: Create the Compiler Module
Create a new directory structure:
```bash
hardware/hw_arch/<your_hw_arch_name>/compilation/
```
Under this directory, create `compiler.py` and declare a subclass of `CompilerBase`:

```python
from app.compilers.base import CompilerBase, CompilationResult

LABEL = "My Hardware Architecture"  # Friendly name displayed in the Web UI

class MyHWArchCompiler(CompilerBase):
    EXECUTION_STRATEGY = "docker"                    # Either "docker" or "python"
    DOCKER_IMAGE = "my-hw-arch-sdk-image:latest"         # Required if strategy is "docker"
    OUTPUT_FORMAT = ".hef"                           # Resulting extension
    SUPPORTED_HARDWARE = ["my_hw_arch_v1", "my_hw_arch_v2"]  # Internal identifier tags
```

### Step 2: Implement the `compile()` Method
Every compiler must implement `async def compile(...)`. The method is responsible for:
1. Downloading the raw `.pt` PyTorch model weights from MinIO.
2. Running the hardware compiler utility (e.g., executing compilation inside a Docker container via `run_subprocess_with_logs`).
3. Uploading the compiled binary to the `compiled` MinIO bucket.
4. Returning a `CompilationResult`.

#### Example Implementation
```python
"""
AURA RPi CPU Compiler.
======================
Compiles/Exports PyTorch neural networks into ONNX format inside Docker container environments for Raspberry Pi 5.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from typing import Any

from app.compilers.base import CompilerBase, CompilationResult
from shared.utils.minio import get_minio, upload_bytes

# Setup logging
logger = logging.getLogger(__name__)

LABEL = "RPi (CPU)"


class RPiCPUCompiler(CompilerBase):
    """
    Compiler executing ONNX export compilation jobs for Raspberry Pi CPU inside Docker.
    """
    EXECUTION_STRATEGY = "docker"
    DOCKER_IMAGE = "ultralytics/ultralytics:latest"
    OUTPUT_FORMAT = ".onnx"
    SUPPORTED_HARDWARE = ["rpi"]

    def __init__(self, minio_bucket_models: str, minio_bucket_compiled: str) -> None:
        """
        Initializes the compiler with bucket storage paths.

        :param minio_bucket_models: MinIO bucket name for raw model files.
        :type minio_bucket_models: str
        :param minio_bucket_compiled: MinIO bucket name for compiled binaries.
        :type minio_bucket_compiled: str
        """
        self._bucket_models = minio_bucket_models
        self._bucket_compiled = minio_bucket_compiled

    async def compile(
        self,
        model_id: str,
        source_key: str,
        num_classes: int,
        class_names: list[str],
        hardware_type: str,
        dataset_id: str,
        dataset_key: str,
        base_architecture: str = "",
        input_size: str = "",
    ) -> CompilationResult:
        """
        Performs the model export/compilation sequence.

        Downloads the .pt model weights, starts an Ultralytics container,
        runs model.export() to generate ONNX, and uploads the output to MinIO.

        :param model_id: Target model ID string.
        :type model_id: str
        :param source_key: Object storage key of original model weights.
        :type source_key: str
        :param num_classes: Total number of prediction categories.
        :type num_classes: int
        :param class_names: Prediction category labels.
        :type class_names: list[str]
        :param hardware_type: Target hardware target.
        :type hardware_type: str
        :param dataset_id: Unique calibration dataset ID.
        :type dataset_id: str
        :param dataset_key: Object storage key of calibration dataset.
        :type dataset_key: str
        :param base_architecture: Base YOLO model architecture.
        :type base_architecture: str
        :param input_size: Desired model resolution (e.g. '640x640').
        :type input_size: str
        :return: Compilation status metrics.
        :rtype: CompilationResult
        """
        logger.info(f"[RPiCPU] Starting compilation for model {model_id}, hw={hardware_type}")

        # Resolve image dimensions
        img_size = 640
        if input_size:
            try:
                parts = input_size.lower().split("x")
                img_size = int(parts[0])
            except Exception:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Download source model (.pt) from MinIO
            pt_path = os.path.join(tmpdir, "model.pt")
            onnx_path = os.path.join(tmpdir, "model.onnx")
            minio = get_minio()
            try:
                await self.log_progress(model_id, "[RPiCPU] Descargando modelo base .pt desde MinIO...")
                await minio.fget_object(self._bucket_models, source_key, pt_path)
            except Exception as e:
                logger.error(f"[RPiCPU] Failed to download source model: {e}")
                return CompilationResult(success=False, error=f"Failed to download source model: {e}")

            container_name = f"compile_{model_id}"
            try:
                # 2. Run the container in detached sleep mode
                run_cmd = [
                    "docker", "run", "-d",
                    "--name", container_name,
                    "--entrypoint", "sleep",
                    self.DOCKER_IMAGE,
                    "3600"
                ]
                logger.info(f"[RPiCPU] Creating Docker container: {' '.join(run_cmd)}")
                await self.log_progress(model_id, "[RPiCPU] Creando contenedor de compilación Docker...")
                proc = await asyncio.create_subprocess_exec(
                    *run_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.error(f"[RPiCPU] Failed to run Docker container: {err_msg}")
                    return CompilationResult(success=False, error=f"Failed to start compiler container: {err_msg}")

                # 3. Copy the .pt file inside
                cp_in_cmd = ["docker", "cp", pt_path, f"{container_name}:/tmp/model.pt"]
                logger.info(f"[RPiCPU] Copying weights to container: {' '.join(cp_in_cmd)}")
                await self.log_progress(model_id, "[RPiCPU] Copiando pesos del modelo al contenedor...")
                proc = await asyncio.create_subprocess_exec(
                    *cp_in_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.error(f"[RPiCPU] Failed to copy weights to container: {err_msg}")
                    return CompilationResult(success=False, error=f"Failed to copy weights to container: {err_msg}")

                # 4. Execute compilation
                # Execute python export script inside the container with unbuffered python (-u)
                exec_cmd = [
                    "docker", "exec", container_name,
                    "python3", "-u", "-c",
                    f"from ultralytics import YOLO; model = YOLO('/tmp/model.pt'); model.export(format='onnx', imgsz={img_size}, batch=1, nms=True, opset=12)"
                ]
                logger.info(f"[RPiCPU] Executing ONNX export in container: {' '.join(exec_cmd)}")
                await self.log_progress(model_id, "[RPiCPU] Iniciando exportación a ONNX (Ultralytics)...")

                returncode = await self.run_subprocess_with_logs(model_id, exec_cmd)

                redis = getattr(self, "redis_client", None)
                cancel_key = f"cancel:compile:{model_id}"
                if redis and await redis.exists(cancel_key):
                    raise asyncio.CancelledError()

                if returncode != 0:
                    logger.error(f"[RPiCPU] ONNX export failed inside container")
                    return CompilationResult(success=False, error="ONNX export failed inside container")

                # 5. Copy the compiled ONNX model back to host
                cp_out_cmd = ["docker", "cp", f"{container_name}:/tmp/model.onnx", onnx_path]
                logger.info(f"[RPiCPU] Copying compiled model back: {' '.join(cp_out_cmd)}")
                proc = await asyncio.create_subprocess_exec(
                    *cp_out_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.error(f"[RPiCPU] Failed to copy compiled model from container: {err_msg}")
                    return CompilationResult(success=False, error=f"Failed to retrieve compiled model: {err_msg}")

            except asyncio.CancelledError:
                logger.warning(f"[RPiCPU] Compilation job for model {model_id} was cancelled.")
                raise
            except Exception as e:
                logger.exception(f"[RPiCPU] Unexpected error during docker compilation: {e}")
                return CompilationResult(success=False, error=f"Docker compilation error: {e}")
            finally:
                # 6. Clean up container
                logger.info(f"[RPiCPU] Cleaning up Docker container {container_name}...")
                cleanup_cmd = ["docker", "rm", "-f", container_name]
                try:
                    cleanup_proc = await asyncio.create_subprocess_exec(
                        *cleanup_cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await cleanup_proc.wait()
                except Exception as e:
                    logger.warning(f"[RPiCPU] Failed to clean up container: {e}")

            # 7. Read compiled ONNX bytes and upload to MinIO
            if not os.path.exists(onnx_path):
                return CompilationResult(success=False, error="ONNX model file not found on host after copy")

            try:
                with open(onnx_path, "rb") as f:
                    onnx_data = f.read()

                sha = hashlib.sha256(onnx_data).hexdigest()
                compiled_key = f"{model_id}/model.onnx"

                logger.info(f"[RPiCPU] Uploading compiled model to MinIO: {compiled_key}...")
                await upload_bytes("compiled", compiled_key, onnx_data)

                logger.info(f"[RPiCPU] Compilation successful -> {compiled_key}")
                return CompilationResult(
                    success=True,
                    compiled_key=compiled_key,
                    compiled_sha256=sha
                )
            except Exception as e:
                logger.exception(f"[RPiCPU] Failed to upload compiled model to MinIO: {e}")
                return CompilationResult(success=False, error=f"Upload failed: {e}")

```

---

## 2. Adding Sensor, Actuator and Others Drivers

AURA dynamically scans connected peripherals so they can be monitored and managed by the Edge Runtime agent.

### Directory Convention
Peripherals must follow this directory pattern:
* **Sensors**: `hardware/sensors/<device_type>/<driver_name>/library.py`
* **Actuators**: `hardware/actuators/<device_type>/<driver_name>/library.py`
* **Others**: `hardware/others/<device_type>/<driver_name>/library.py`

Where:
* `<device_type>` is the type/category classification of the peripheral (e.g., `camera`, `gps`, `temperature`).
* `<driver_name>` is the name of the specific driver implementation (e.g., `imx500`, `bme280`, `gps_simulated`).

### Step 1: Create `library.py`
Define a class in `library.py` representing your peripheral device. It must define a module-level variable `LABEL`.

```python
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
```

### Step 2: Graceful Mock Fallback
Since developers test the platform on different OS environments, drivers must not crash when native system dependencies are missing (e.g. SMBus packages on a standard dev laptop). Always implement a fallback to a simulated/mock driver in case of `ImportError`.

---

## 3. Integrating with the Hardware Daemon

When running the Edge Agent inside a Docker container, accessing native host hardware resources (such as cameras and hardware accelerators like Hailo-8 or IMX500) can be complex and typically requires privileged container flags or complex device mounts.

AURA solves this by running a lightweight host-level **Hardware Daemon** (`hardware_daemon.py`). The daemon runs directly on the host operating system, interfaces with native drivers (e.g. `picamera2`), and exposes a local HTTP API for the containerized Edge Agent.

The standard daemon API includes:
* `GET /capture`: Returns the latest camera frame as raw image bytes.
* `GET /status`: Returns a JSON object with system capability details.
* `POST /load`: Accepts model bytes (such as a compiled HEF) and initializes the hardware context.
* `POST /infer`: Performs inference on input RGB bytes and returns model outputs.
* `POST /unload`: Cleans up the hardware context.

### Extending the Daemon for New Accelerators

If you are adding a new hardware accelerator that cannot be accessed directly from inside Docker, you should extend the Hardware Daemon:

1. **Create a manager module** under `edge-runtime/daemon/<your_accelerator>.py`.
2. **Implement your manager class** and instantiate a global singleton instance ending in `_manager` (for example, `my_accel_manager = MyAcceleratorManager()`). The daemon's `__init__.py` will automatically scan and export it.
3. **Update the HTTP Router** in `hardware_daemon.py` to forward requests from `/load` or `/infer` to your manager based on the active `AURA_HARDWARE_TYPE` environment variable.

### Extending the Daemon for New Peripherals

If you have a physical sensor or actuator connected to the host (via I2C, SPI, GPIO, etc.) that requires native Python libraries not available (or difficult to share) inside the Docker container, you can expose it using the Hardware Daemon:

1. **Create a new peripheral manager** under `edge-runtime/daemon/<your_peripheral_name>.py`.
2. **Implement the initialization and read/write methods** (using native host libraries like `smbus2` or `RPi.GPIO`).
3. **Instantiate a global singleton manager** ending with `_manager` (e.g. `env_sensor_manager = EnvSensorManager()`) in your module so that `daemon/__init__.py` automatically loads and exposes it.
4. **Expose custom endpoints in `hardware_daemon.py`**:
   - In `do_GET(self)`, add a path handler to retrieve values (e.g., `GET /sensor/env` routing to `env_sensor_manager.read_value()`).
   - In `do_POST(self)`, add a path handler to receive commands (e.g., `POST /actuate` routing to `actuator_manager.write_value()`).
5. **Update your containerized proxy driver**: In `hardware/sensors/<device_type>/<driver_name>/library.py` (which runs inside the container), implement the `read_value` method to make an HTTP request to the host gateway daemon (e.g., `http://<gateway_ip>:8008/sensor/env`) to fetch the measurements.

---

## 4. Registering components config

When running on an edge device, the active driver and parameters are configured in the `components_config.yaml` file located in the configuration directory of the agent. The PAL wrapper reads the current layout and dynamically resolves and runs the specified drivers.
