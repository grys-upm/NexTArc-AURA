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
                compiled_key = f"{model_id}/model_{hardware_type}.onnx"

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
