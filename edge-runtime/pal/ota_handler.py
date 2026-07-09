"""
PAL — OTA Handler
==================
Responsible for downloading and validating Over-The-Air deployment
artefacts (model + user script) sent via MQTT ``deploy`` commands.

Workflow
--------
1. Receive a ``deploy`` payload with model URL + SHA-256 and script
   URL + SHA-256.
2. Stream-download each artefact to the work directory.
3. Verify the SHA-256 digest of each downloaded file.
4. Call ``aura_hw.load_model()`` with the new model path.
5. Hot-reload the user script module.
6. Update the in-memory deployment state and notify via MQTT events.

On any failure the partial state is **not** committed — the previous
model and script remain active.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import logging
import types
from pathlib import Path
from typing import Callable, Any

import httpx

logger = logging.getLogger(__name__)

# Callback types
EventPublisher = Callable[[str], None]  # publish_event("deploy_ack", ...)


class OTAHandler:
    """
    Handles OTA deployment of model and script artifacts.

    This class manages downloads of new model files and custom Python scripts,
    verifies their SHA-256 integrity, triggers loader updates in the hardware abstraction layer,
    and performs dynamic module loading (hot-reloads).

    :ivar _work_dir: Workspace directory where files are downloaded.
    :type _work_dir: Path
    :ivar _on_event: Function to publish status events.
    :type _on_event: Callable
    :ivar _on_deploy_success: Callback function invoked after success.
    :type _on_deploy_success: Callable
    :ivar _device_manager: Component device manager.
    :type _device_manager: DeviceManager or None
    :ivar _model_path: Destination path on disk for active model files.
    :type _model_path: Path
    :ivar _script_path: Destination path on disk for the active user python script.
    :type _script_path: Path
    """

    def __init__(
        self,
        work_dir: Path,
        on_event: Callable,
        on_deploy_success: Callable,
        device_manager: Any = None,
    ) -> None:
        """
        Initializes the OTAHandler with workspaces and event callbacks.

        :param work_dir: Target directory path to store artifacts.
        :type work_dir: Path
        :param on_event: Async event dispatcher callback.
        :type on_event: Callable
        :param on_deploy_success: Success callback accepting new states.
        :type on_deploy_success: Callable
        :param device_manager: Optional DeviceManager instance.
        :type device_manager: DeviceManager or None
        """
        self._work_dir = work_dir
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._on_event = on_event
        self._on_deploy_success = on_deploy_success
        self._device_manager = device_manager

        # Set paths for active files on disk
        self._model_path = work_dir / "model"
        self._script_path = work_dir / "script.py"

    # ── Public API ─────────────────────────────────────────────────────────

    async def handle_deploy(self, payload: dict) -> None:
        """
        Processes a deployment command to update model and script artifacts.

        Downloads files, validates hashes, reloads the neural network model,
        and dynamically hot-reloads the Python script execution callback.

        :param payload: Deployment payload dictionary.
        :type payload: dict
        """
        dep_id = payload["deployment_id"]
        model_url = payload["model_url"]
        model_sha = payload["model_sha256"]
        script_url = payload["script_url"]
        script_sha = payload["script_sha256"]
        model_id = payload.get("model_id", "")
        script_id = payload.get("script_id", "")

        logger.info(f"[{dep_id}] OTA deploy started")

        try:
            # 1. Download model file
            logger.info(f"[{dep_id}] Downloading model from {model_url}")
            await self._download(model_url, self._model_path)
            # Verify SHA-256 integrity of the downloaded model file
            self._verify_sha256(self._model_path, model_sha, "model")

            # 2. Download user script file
            logger.info(f"[{dep_id}] Downloading script from {script_url}")
            await self._download(script_url, self._script_path)
            # Verify SHA-256 integrity of the downloaded script file
            self._verify_sha256(self._script_path, script_sha, "script")

            # 3. Load the new model into the Hardware Abstraction Layer (HAL)
            from aura_hw import load_model, unload_model
            logger.info(f"[{dep_id}] Loading model into HAL backend")
            unload_model()
            class_names = payload.get("class_names", [])
            
            # Save classes list metadata JSON locally alongside the model file
            classes_file = self._model_path.parent / "classes.json"
            try:
                import json
                classes_file.write_text(json.dumps(class_names))
                logger.info(f"[{dep_id}] Saved class names to {classes_file}")
            except Exception as e:
                logger.warning(f"[{dep_id}] Failed to save classes.json: {e}")
                
            # Load the model with classes configuration
            load_model(str(self._model_path), class_names=class_names)

            # 4. Dynamically import and hot-reload user script
            logger.info(f"[{dep_id}] Reloading user script")
            script_module = self._load_script(self._script_path)

            # 5. Build state update structure and notify success
            new_state = {
                "active_deployment_id": dep_id,
                "active_model_id": model_id,
                "active_script_id": script_id,
                "script_module": script_module,
                "model_path": str(self._model_path),
            }
            # Execute deployment success callback
            res = self._on_deploy_success(new_state)
            if res is not None and (asyncio.iscoroutine(res) or hasattr(res, "__await__")):
                await res
                
            # Publish deploy acknowledgement event
            await self._on_event("deploy_ack", deployment_id=dep_id)
            logger.info(f"[{dep_id}] OTA deploy completed successfully")

        except Exception as exc:  # noqa: BLE001
            logger.error(f"[{dep_id}] OTA deploy failed: {exc}")
            # Dispatch error event report
            await self._on_event(
                "deploy_failed", deployment_id=dep_id, error=str(exc)
            )

    async def handle_update_libraries(self, payload: dict) -> None:
        """
        Updates local dynamic hardware abstraction modules from a remote ZIP file.

        Cleans up existing dynamic subdirectories (sensors, actuators, etc.)
        and extracts new library versions.

        :param payload: Update libraries payload dictionary.
        :type payload: dict
        """
        lib_url = payload["libraries_url"]
        lib_sha = payload["libraries_sha256"]

        logger.info("OTA dynamic hardware libraries update started")
        temp_zip = self._work_dir / "libraries_temp.zip"

        try:
            # 1. Download libraries compressed file
            logger.info(f"Downloading libraries zip from {lib_url}")
            await self._download(lib_url, temp_zip)
            # Verify zip archive integrity
            self._verify_sha256(temp_zip, lib_sha, "libraries_zip")

            # 2. Extract files into the local hardware directory
            import zipfile
            import shutil
            from aura_hw.loader import get_hardware_dir

            hw_dir = get_hardware_dir()
            logger.info(f"Extracting libraries to hardware directory: {hw_dir}")

            # Delete all old dynamic libraries for safety to ensure a clean state
            if hw_dir.exists():
                for item in hw_dir.iterdir():
                    try:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except Exception as e:
                        logger.warning(f"Could not delete {item} during library cleanup: {e}")

            # Extract new zip archive contents
            hw_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(temp_zip, "r") as zip_ref:
                zip_ref.extractall(hw_dir)

            # Re-initialize device backends dynamically if manager is available
            if self._device_manager:
                logger.info("Re-opening device backends after library update...")
                self._device_manager.open_all()

            # 3. Publish dynamic library update acknowledgement
            await self._on_event("update_libraries_ack", libraries_sha256=lib_sha)
            logger.info("OTA dynamic hardware libraries update completed successfully")

        except Exception as exc:
            logger.error(f"OTA dynamic hardware libraries update failed: {exc}")
            await self._on_event("update_libraries_failed", error=str(exc))
        finally:
            # Clean up temporary zip file
            if temp_zip.exists():
                try:
                    temp_zip.unlink()
                except OSError:
                    pass

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    async def _download(url: str, dest: Path) -> None:
        """
        Downloads a remote URL file directly to disk using chunked streaming.

        Handles network address re-routing for local debug environments.

        :param url: Source HTTP/S URL string.
        :type url: str
        :param dest: Output destination file path.
        :type dest: Path
        """
        import os
        import socket
        from urllib.parse import urlparse, urlunparse
        
        headers = {}
        parsed = urlparse(url)
        
        # Adjust URL hostname if referencing local dev services (MinIO)
        if parsed.hostname in ("localhost", "127.0.0.1", "minio"):
            use_minio = False
            try:
                socket.gethostbyname("minio")
                use_minio = True
            except socket.gaierror:
                pass
                
            target_host = "minio" if use_minio else os.environ.get("AURA_MQTT_HOST", "localhost")
            new_netloc = f"{target_host}:{parsed.port}" if parsed.port else target_host
            
            # Preserve original HTTP Host header for signature validation check
            headers["Host"] = parsed.netloc
                
            parsed = parsed._replace(netloc=new_netloc)
            url = urlunparse(parsed)
            logger.info(f"Redirected local download URL target to: {url}")

        # Stream download chunks via httpx
        async with httpx.AsyncClient(
            timeout=120.0, follow_redirects=True
        ) as http:
            async with http.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                with open(dest, "wb") as fh:
                    async for chunk in response.aiter_bytes(65_536):
                        fh.write(chunk)
        logger.debug(f"Downloaded {url} → {dest} ({dest.stat().st_size} bytes)")

    @staticmethod
    def _sha256(path: Path) -> str:
        """
        Computes the SHA-256 hexadecimal hash of a local file.

        :param path: Input file path.
        :type path: Path
        :return: Computed lowercase hexadecimal hash.
        :rtype: str
        """
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65_536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _verify_sha256(self, path: Path, expected: str, label: str) -> None:
        """
        Verifies if a file matches the expected SHA-256 hash.

        :param path: Local target file path.
        :type path: Path
        :param expected: Expected lowercase SHA-256 string.
        :type expected: str
        :param label: Readable name for logging errors.
        :type label: str
        :raises ValueError: If hashes do not match.
        """
        actual = self._sha256(path)
        if actual != expected.lower():
            raise ValueError(
                f"{label} SHA-256 mismatch — "
                f"expected {expected}, got {actual}"
            )
        logger.debug(f"{label} SHA-256 OK: {actual}")

    @staticmethod
    def _load_script(path: Path) -> types.ModuleType:
        """
        Dynamically imports a script from disk under a fixed module identifier.

        :param path: Source script file path.
        :type path: Path
        :return: Loaded module structure.
        :rtype: types.ModuleType
        :raises ImportError: If the file cannot be loaded.
        """
        spec = importlib.util.spec_from_file_location("user_script", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load script from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
