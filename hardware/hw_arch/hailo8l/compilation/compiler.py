"""
AURA Hailo-8L Compiler.
=======================
Compiles neural networks into Hailo-8L HEF binaries using Docker container environments.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import tempfile
import zipfile
from typing import Any

from PIL import Image
from app.compilers.base import CompilerBase, CompilationResult
from shared.utils.minio import get_minio, upload_bytes

# Setup logging
logger = logging.getLogger(__name__)

LABEL = "Hailo-8L"


class Hailo8LCompiler(CompilerBase):
    """
    Compiler executing Hailo-8L MLOps build jobs within a specialized Docker environment.
    """
    EXECUTION_STRATEGY = "docker"
    DOCKER_IMAGE = "hailo8_ai_sw_suite_2025-10:1"
    OUTPUT_FORMAT = ".hef"
    SUPPORTED_HARDWARE = ["hailo8l"]

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
        Performs the model compilation sequence.

        Downloads the .pt model weights, converts them to ONNX, prepares dataset
        calibration images, starts a compiler container, compiles to HEF,
        and uploads the output binary to MinIO object storage.

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
        logger.info(f"[Hailo8L] Starting compilation for model {model_id}, hw={hardware_type}")

        # Resolve image dimensions
        img_size = 640
        if input_size:
            try:
                parts = input_size.lower().split("x")
                img_size = int(parts[0])
            except Exception:
                pass

        # Resolve model configuration YAML name based on target base architecture
        yaml_name = "yolov8n.yaml"
        if base_architecture:
            base_lower = base_architecture.lower()
            base_name = os.path.splitext(base_lower)[0]
            if "yolov8" in base_name:
                size = "n"
                for s in ["n", "s", "m", "l", "x"]:
                    if f"yolov8{s}" in base_name:
                        size = s
                        break
                yaml_name = f"yolov8{size}.yaml"
            elif "yolov11" in base_name or "yolo11" in base_name:
                size = "n"
                for s in ["n", "s", "m", "l", "x"]:
                    if f"yolov11{s}" in base_name or f"yolo11{s}" in base_name:
                        size = s
                        break
                yaml_name = f"yolov11{size}.yaml"
            else:
                yaml_name = f"{base_name}.yaml"

        redis = getattr(self, "redis_client", None)
        cancel_key = f"cancel:compile:{model_id}"

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Download source model (.pt) from MinIO
            pt_path = os.path.join(tmpdir, "model.pt")
            minio = get_minio()
            try:
                await self.log_progress(model_id, "[Hailo8L] Descargando modelo base .pt desde MinIO...")
                await minio.fget_object(self._bucket_models, source_key, pt_path)
            except Exception as e:
                logger.error(f"[Hailo8L] Failed to download source model: {e}")
                return CompilationResult(success=False, error=f"Failed to download source model: {e}")

            if redis and await redis.exists(cancel_key):
                raise asyncio.CancelledError()

            # 2. Export PT model to ONNX locally (using MLOps container python)
            logger.info(f"[Hailo8L] Exporting model to ONNX with nms=False, opset=11, batch=1...")
            await self.log_progress(model_id, "[Hailo8L] Exportando modelo .pt a ONNX (Ultralytics)...")
            try:
                from ultralytics import YOLO
                model = YOLO(pt_path)
                onnx_path = model.export(format="onnx", imgsz=img_size, batch=1, nms=False, opset=11)
            except Exception as e:
                logger.exception(f"[Hailo8L] ONNX export failed: {e}")
                return CompilationResult(success=False, error=f"ONNX export failed: {e}")

            if redis and await redis.exists(cancel_key):
                raise asyncio.CancelledError()

            # 3. Download and prepare calibration images
            calib_dir = os.path.join(tmpdir, "calib")
            os.makedirs(calib_dir, exist_ok=True)
            if not dataset_key:
                logger.error("[Hailo8L] Dataset key is required for calibration data generation")
                return CompilationResult(success=False, error="Dataset key is required for Hailo compiler")

            try:
                zip_path = os.path.join(tmpdir, "dataset.zip")
                dataset_extract_dir = os.path.join(tmpdir, "dataset")
                logger.info(f"[Hailo8L] Downloading dataset {dataset_key} for calibration...")
                await self.log_progress(model_id, "[Hailo8L] Descargando y preparando imágenes para calibración...")
                await minio.fget_object("datasets", dataset_key, zip_path)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(dataset_extract_dir)

                extensions = {'.jpg', '.jpeg', '.png'}
                all_images = [
                    os.path.join(root, f)
                    for root, _, files in os.walk(dataset_extract_dir)
                    for f in files if os.path.splitext(f)[1].lower() in extensions
                ]

                if not all_images:
                    raise ValueError("No images found in dataset zip")

                random.shuffle(all_images)
                selected_images = all_images[:1024]
                logger.info(f"[Hailo8L] Generating calibration images from {len(selected_images)} frames...")

                for idx, img_path in enumerate(selected_images):
                    try:
                        with Image.open(img_path) as img:
                            img.verify()
                        with Image.open(img_path) as img:
                            img = img.convert("RGB")
                            ratio = max(img_size / img.width, img_size / img.height)
                            new_w, new_h = int(img.width * ratio), int(img.height * ratio)
                            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                            left = (img.width - img_size) // 2
                            top = (img.height - img_size) // 2
                            img = img.crop((left, top, left + img_size, top + img_size))
                            img.save(os.path.join(calib_dir, f"calib_{idx}.jpg"), format="JPEG", quality=95)
                    except Exception:
                        continue
            except Exception as e:
                logger.exception(f"[Hailo8L] Calibration preparation failed: {e}")
                return CompilationResult(success=False, error=f"Calibration preparation failed: {e}")

            if redis and await redis.exists(cancel_key):
                raise asyncio.CancelledError()

            # 4. Prepare Docker run for compilation
            container_name = f"compile_{model_id}"
            hef_path = os.path.join(tmpdir, "model.hef")
            
            try:
                # Run the container in detached sleep mode
                run_cmd = [
                    "docker", "run", "-d",
                    "--name", container_name,
                    "--entrypoint", "sleep",
                    self.DOCKER_IMAGE,
                    "3600"
                ]
                logger.info(f"[Hailo8L] Creating Docker container: {' '.join(run_cmd)}")
                await self.log_progress(model_id, "[Hailo8L] Creando contenedor Docker para compilador Hailo Model Zoo...")
                proc = await asyncio.create_subprocess_exec(
                    *run_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.error(f"[Hailo8L] Failed to run Docker container: {err_msg}")
                    return CompilationResult(success=False, error=f"Failed to start compiler container: {err_msg}")

                # Copy files inside
                logger.info(f"[Hailo8L] Copying ONNX model and calibration images to container...")
                await self.log_progress(model_id, "[Hailo8L] Copiando modelo ONNX e imágenes de calibración al contenedor...")
                cp_model_cmd = ["docker", "cp", onnx_path, f"{container_name}:/tmp/model.onnx"]
                proc = await asyncio.create_subprocess_exec(
                    *cp_model_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

                cp_calib_cmd = ["docker", "cp", calib_dir, f"{container_name}:/tmp/calib"]
                proc = await asyncio.create_subprocess_exec(
                    *cp_calib_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

                # Execute compilation inside container using python to find generated .hef safely
                py_script = (
                    "import subprocess, glob, shutil, sys\n"
                    "try:\n"
                    "    cmd = ['hailomz', 'compile', '--ckpt', '/tmp/model.onnx', '--calib-path', '/tmp/calib', "
                    f"'--yaml', '/local/workspace/hailo_model_zoo/hailo_model_zoo/cfg/networks/{yaml_name}', '--classes', '{num_classes}', '--hw-arch', 'hailo8l']\n"
                    "    print('Running compile command inside container...')\n"
                    "    subprocess.run(['bash', '-lc', ' '.join(cmd)], check=True)\n"
                    "    hefs = glob.glob('*.hef') + glob.glob('**/*.hef', recursive=True)\n"
                    "    if not hefs:\n"
                    "        raise FileNotFoundError('No HEF file generated')\n"
                    "    shutil.copy(hefs[0], '/tmp/model.hef')\n"
                    "    print('Successfully copied compiled HEF to /tmp/model.hef')\n"
                    "except Exception as e:\n"
                    "    print('Compilation error:', e, file=sys.stderr)\n"
                    "    sys.exit(1)\n"
                )

                exec_cmd = [
                    "docker", "exec", container_name,
                    "python3", "-u", "-c", py_script
                ]
                logger.info(f"[Hailo8L] Executing compile script in container...")
                await self.log_progress(model_id, "[Hailo8L] Ejecutando compilación de red neuronal en contenedor Hailo...")

                returncode = await self.run_subprocess_with_logs(model_id, exec_cmd)

                if redis and await redis.exists(cancel_key):
                    raise asyncio.CancelledError()

                if returncode != 0:
                    logger.error(f"[Hailo8L] Compile failed inside container")
                    return CompilationResult(success=False, error="Hailo compilation failed inside container")

                # Copy model back to host
                cp_out_cmd = ["docker", "cp", f"{container_name}:/tmp/model.hef", hef_path]
                logger.info(f"[Hailo8L] Copying compiled HEF model back to host...")
                proc = await asyncio.create_subprocess_exec(
                    *cp_out_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    return CompilationResult(success=False, error=f"Failed to copy compiled HEF from container: {err_msg}")

            except asyncio.CancelledError:
                logger.warning(f"[Hailo8L] Compilation job for model {model_id} was cancelled.")
                raise
            except Exception as e:
                logger.exception(f"[Hailo8L] Unexpected error during docker compilation: {e}")
                return CompilationResult(success=False, error=f"Docker compilation error: {e}")
            finally:
                # Clean up container
                logger.info(f"[Hailo8L] Cleaning up Docker container {container_name}...")
                cleanup_cmd = ["docker", "rm", "-f", container_name]
                try:
                    cleanup_proc = await asyncio.create_subprocess_exec(
                        *cleanup_cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await cleanup_proc.wait()
                except Exception as e:
                    logger.warning(f"[Hailo8L] Failed to clean up container: {e}")

            # 5. Read compiled HEF bytes and upload to MinIO
            if not os.path.exists(hef_path):
                return CompilationResult(success=False, error="HEF model file not found on host after copy")

            try:
                with open(hef_path, "rb") as f:
                    hef_data = f.read()

                sha = hashlib.sha256(hef_data).hexdigest()
                compiled_key = f"{model_id}/model_{hardware_type}.hef"

                logger.info(f"[Hailo8L] Uploading compiled model to MinIO: {compiled_key}...")
                await upload_bytes("compiled", compiled_key, hef_data)

                logger.info(f"[Hailo8L] Compilation successful -> {compiled_key}")
                return CompilationResult(
                    success=True,
                    compiled_key=compiled_key,
                    compiled_sha256=sha
                )
            except Exception as e:
                logger.exception(f"[Hailo8L] Failed to upload compiled model to MinIO: {e}")
                return CompilationResult(success=False, error=f"Upload failed: {e}")
