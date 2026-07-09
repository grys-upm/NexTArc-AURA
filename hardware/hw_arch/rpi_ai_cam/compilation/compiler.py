"""
AURA RPi AI Camera Compiler.
============================
Compiles/Exports PyTorch neural networks into Sony IMX500 RPK firmware binaries.
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

LABEL = "RPi AI Camera (Sony IMX500)"


class RPiAICamCompiler(CompilerBase):
    """
    Compiler executing Sony IMX500 compilation and packaging jobs within specialized Docker environments.
    """
    EXECUTION_STRATEGY = "docker"
    DOCKER_IMAGE = "ultralytics/ultralytics:latest"
    OUTPUT_FORMAT = ".rpk"
    SUPPORTED_HARDWARE = ["rpi_ai_cam"]

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

        Downloads weights, exports them using MCT/IMX converter tools inside Docker,
        packages the packerOut.zip into network.rpk using an ARM64 debian container,
        and uploads the output RPK file to MinIO.

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
        logger.info(f"[RPiAICam] Starting compilation for model {model_id}, hw={hardware_type}")

        # Resolve image dimensions
        img_size = 640
        if input_size:
            try:
                parts = input_size.lower().split("x")
                img_size = int(parts[0])
            except Exception:
                pass

        redis = getattr(self, "redis_client", None)
        cancel_key = f"cancel:compile:{model_id}"

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Download source model (.pt) from MinIO
            pt_path = os.path.join(tmpdir, "model.pt")
            minio = get_minio()
            try:
                await self.log_progress(model_id, "[RPiAICam] Descargando modelo base .pt desde MinIO...")
                await minio.fget_object(self._bucket_models, source_key, pt_path)
            except Exception as e:
                logger.error(f"[RPiAICam] Failed to download source model: {e}")
                return CompilationResult(success=False, error=f"Failed to download source model: {e}")

            if redis and await redis.exists(cancel_key):
                raise asyncio.CancelledError()

            # 2. Download and prepare calibration images
            calib_dir = os.path.join(tmpdir, "dataset", "images", "calib_temp")
            os.makedirs(calib_dir, exist_ok=True)
            if not dataset_key:
                logger.error("[RPiAICam] Dataset key is required for calibration data generation")
                return CompilationResult(success=False, error="Dataset key is required for IMX500 compiler")

            try:
                zip_path = os.path.join(tmpdir, "dataset.zip")
                dataset_extract_dir = os.path.join(tmpdir, "dataset_raw")
                logger.info(f"[RPiAICam] Downloading dataset {dataset_key} for calibration...")
                await self.log_progress(model_id, "[RPiAICam] Descargando y preparando imágenes para calibración...")
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
                selected_images = all_images[:300]  # Standard AI Cam calibration uses 300 images
                logger.info(f"[RPiAICam] Generating calibration images from {len(selected_images)} frames...")

                for idx, img_path in enumerate(selected_images):
                    try:
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
                logger.exception(f"[RPiAICam] Calibration preparation failed: {e}")
                return CompilationResult(success=False, error=f"Calibration preparation failed: {e}")

            if redis and await redis.exists(cancel_key):
                raise asyncio.CancelledError()

            # 3. Create dynamic yaml inside tmpdir/dataset
            yaml_content = f"""
path: /tmp/dataset
train: images/calib_temp
val: images/calib_temp

names:
"""
            for i, cls in enumerate(class_names or ["object"]):
                yaml_content += f"  {i}: '{cls}'\n"
            
            yaml_path = os.path.join(tmpdir, "auto_calibration_data.yaml")
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            # 4. Prepare Docker run for compilation
            container_name = f"compile_{model_id}"
            zip_out_path = os.path.join(tmpdir, "packerOut.zip")
            
            try:
                # Run the container in detached sleep mode
                run_cmd = [
                    "docker", "run", "-d",
                    "--name", container_name,
                    "--entrypoint", "sleep",
                    self.DOCKER_IMAGE,
                    "3600"
                ]
                logger.info(f"[RPiAICam] Creating Docker container: {' '.join(run_cmd)}")
                await self.log_progress(model_id, "[RPiAICam] Creando contenedor Docker para compilador Sony IMX500...")
                proc = await asyncio.create_subprocess_exec(
                    *run_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.error(f"[RPiAICam] Failed to run Docker container: {err_msg}")
                    return CompilationResult(success=False, error=f"Failed to start compiler container: {err_msg}")

                # Copy files inside
                logger.info(f"[RPiAICam] Copying model, yaml and calibration dataset to container...")
                await self.log_progress(model_id, "[RPiAICam] Copiando pesos, YAML y dataset de calibración al contenedor...")
                
                # Copy model.pt
                cp_model_cmd = ["docker", "cp", pt_path, f"{container_name}:/tmp/model.pt"]
                proc = await asyncio.create_subprocess_exec(*cp_model_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc.communicate()

                # Copy calibration dataset folder
                cp_dataset_cmd = ["docker", "cp", os.path.join(tmpdir, "dataset"), f"{container_name}:/tmp/dataset"]
                proc = await asyncio.create_subprocess_exec(*cp_dataset_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc.communicate()

                # Copy yaml file
                cp_yaml_cmd = ["docker", "cp", yaml_path, f"{container_name}:/tmp/auto_calibration_data.yaml"]
                proc = await asyncio.create_subprocess_exec(*cp_yaml_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc.communicate()

                # Execute compilation inside container
                py_script = (
                    "import subprocess, glob, shutil, os, sys\n"
                    "try:\n"
                    "    print('Installing Sony IMX500 compilation packages...')\n"
                    "    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'model-compression-toolkit', 'imx500-converter[pt]'], check=True)\n"
                    "    from ultralytics import YOLO\n"
                    "    model = YOLO('/tmp/model.pt')\n"
                    "    print('Running export for IMX500...')\n"
                    "    model.export(format='imx', data='/tmp/auto_calibration_data.yaml')\n"
                    "    zips = glob.glob('/tmp/**/packerOut.zip', recursive=True) + glob.glob('**/packerOut.zip', recursive=True)\n"
                    "    if not zips:\n"
                    "         raise FileNotFoundError('packerOut.zip not found after export')\n"
                    "    shutil.copy(zips[0], '/tmp/packerOut.zip')\n"
                    "    print('Successfully copied packerOut.zip to /tmp/packerOut.zip')\n"
                    "except Exception as e:\n"
                    "    import traceback\n"
                    "    traceback.print_exc()\n"
                    "    sys.exit(1)\n"
                )

                exec_cmd = [
                    "docker", "exec", container_name,
                    "python3", "-u", "-c", py_script
                ]
                logger.info(f"[RPiAICam] Executing compile script in container...")
                await self.log_progress(model_id, "[RPiAICam] Instalando dependencias y exportando modelo a formato IMX500...")

                returncode = await self.run_subprocess_with_logs(model_id, exec_cmd)

                if redis and await redis.exists(cancel_key):
                    raise asyncio.CancelledError()

                if returncode != 0:
                    logger.error(f"[RPiAICam] Compile failed inside container")
                    return CompilationResult(success=False, error="IMX500 compilation failed inside container")

                # Copy model back to host
                cp_out_cmd = ["docker", "cp", f"{container_name}:/tmp/packerOut.zip", zip_out_path]
                logger.info(f"[RPiAICam] Copying packerOut.zip back to host...")
                proc = await asyncio.create_subprocess_exec(*cp_out_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc.communicate()
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    return CompilationResult(success=False, error=f"Failed to copy compiled ZIP from container: {err_msg}")

                # Ensure the packaging image exists
                logger.info("[RPiAICam] Checking if aura-imx500-packager exists...")
                check_img = await asyncio.create_subprocess_exec(
                    "docker", "image", "inspect", "aura-imx500-packager",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await check_img.wait()
                if check_img.returncode != 0:
                    logger.info("[RPiAICam] aura-imx500-packager not found. Building it (runs once)...")
                    dockerfile_content = (
                        "FROM --platform=linux/arm64 debian:bookworm-slim\n"
                        "RUN apt-get update && apt-get install -y curl gnupg \\\n"
                        "    && curl -fsSL http://archive.raspberrypi.org/debian/raspberrypi.gpg.key | gpg --dearmor -o /usr/share/keyrings/raspberrypi-archive-keyring.gpg \\\n"
                        "    && echo 'deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.gpg] http://archive.raspberrypi.org/debian/ bookworm main' > /etc/apt/sources.list.d/raspi.list \\\n"
                        "    && apt-get update \\\n"
                        "    && apt-get install -y imx500-tools \\\n"
                        "    && rm -rf /var/lib/apt/lists/*\n"
                        "WORKDIR /workspace\n"
                        "ENTRYPOINT [\"imx500-package\"]\n"
                    )
                    dockerfile_path = os.path.join(tmpdir, "Dockerfile.packager")
                    with open(dockerfile_path, "w") as f:
                        f.write(dockerfile_content)
                    
                    build_proc = await asyncio.create_subprocess_exec(
                        "docker", "build", "--platform", "linux/arm64", "-t", "aura-imx500-packager", "-f", dockerfile_path, tmpdir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout_b, stderr_b = await build_proc.communicate()
                    if build_proc.returncode != 0:
                        logger.error(f"[RPiAICam] Failed to build packager image: {stderr_b.decode()}")
                        return CompilationResult(success=False, error=f"Failed to build RPK packager image: {stderr_b.decode()}")
                    logger.info("[RPiAICam] Successfully built aura-imx500-packager image.")

                # Run package command using container cp and exec (DinD safe)
                logger.info("[RPiAICam] Packaging packerOut.zip into network.rpk inside ARM64 container...")
                rpk_out_path = os.path.join(tmpdir, "network.rpk")
                pack_container_name = f"package_{model_id}"
                
                # 1. Start packaging container in sleep mode
                run_pack_cmd = [
                    "docker", "run", "-d",
                    "--name", pack_container_name,
                    "--platform", "linux/arm64",
                    "--entrypoint", "sleep",
                    "aura-imx500-packager",
                    "3600"
                ]
                proc_p = await asyncio.create_subprocess_exec(*run_pack_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout_p, stderr_p = await proc_p.communicate()
                if proc_p.returncode != 0:
                    err_msg = stderr_p.decode().strip()
                    return CompilationResult(success=False, error=f"Failed to start RPK packager container: {err_msg}")

                try:
                    # 2. Copy packerOut.zip into the packager container
                    cp_pack_in = ["docker", "cp", zip_out_path, f"{pack_container_name}:/workspace/packerOut.zip"]
                    proc_p = await asyncio.create_subprocess_exec(*cp_pack_in, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    await proc_p.communicate()

                    # 3. Execute imx500-package inside the container
                    exec_pack_cmd = [
                        "docker", "exec", pack_container_name,
                        "imx500-package", "-i", "/workspace/packerOut.zip", "-o", "/workspace"
                    ]
                    proc_p = await asyncio.create_subprocess_exec(*exec_pack_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    stdout_p, stderr_p = await proc_p.communicate()
                    if proc_p.returncode != 0:
                        err_msg = stderr_p.decode().strip()
                        logger.error(f"[RPiAICam] RPK packaging failed: {err_msg}\nStdout: {stdout_p.decode()}")
                        return CompilationResult(success=False, error=f"RPK packaging failed: {err_msg}")

                    # 4. Copy network.rpk back to the host
                    cp_pack_out = ["docker", "cp", f"{pack_container_name}:/workspace/network.rpk", rpk_out_path]
                    proc_p = await asyncio.create_subprocess_exec(*cp_pack_out, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    await proc_p.communicate()
                    logger.info("[RPiAICam] Packaging completed successfully.")

                finally:
                    # 5. Clean up packager container
                    cleanup_proc = await asyncio.create_subprocess_exec(
                        "docker", "rm", "-f", pack_container_name,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await cleanup_proc.wait()

            except asyncio.CancelledError:
                logger.warning(f"[RPiAICam] Compilation job for model {model_id} was cancelled.")
                raise
            except Exception as e:
                logger.exception(f"[RPiAICam] Unexpected error during docker compilation: {e}")
                return CompilationResult(success=False, error=f"Docker compilation error: {e}")
            finally:
                # Clean up container
                logger.info(f"[RPiAICam] Cleaning up Docker container {container_name}...")
                cleanup_cmd = ["docker", "rm", "-f", container_name]
                try:
                    cleanup_proc = await asyncio.create_subprocess_exec(
                        *cleanup_cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await cleanup_proc.wait()
                except Exception as e:
                    logger.warning(f"[RPiAICam] Failed to clean up container: {e}")

            # 5. Read compiled RPK bytes and upload to MinIO
            if not os.path.exists(rpk_out_path):
                return CompilationResult(success=False, error="network.rpk file not found on host after packaging")

            try:
                with open(rpk_out_path, "rb") as f:
                    rpk_data = f.read()

                sha = hashlib.sha256(rpk_data).hexdigest()
                compiled_key = f"{model_id}/model_{hardware_type}.rpk"

                logger.info(f"[RPiAICam] Uploading compiled model to MinIO: {compiled_key}...")
                await upload_bytes("compiled", compiled_key, rpk_data)

                logger.info(f"[RPiAICam] Compilation successful -> {compiled_key}")
                return CompilationResult(
                    success=True,
                    compiled_key=compiled_key,
                    compiled_sha256=sha
                )
            except Exception as e:
                logger.exception(f"[RPiAICam] Failed to upload compiled model to MinIO: {e}")
                return CompilationResult(success=False, error=f"Upload failed: {e}")
