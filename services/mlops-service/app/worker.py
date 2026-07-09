"""ARQ task runner and queue background job executors for the MLOps Service.

Defines the worker loop, enqueued training jobs, enqueued hardware-specific model
compilations, log streams, and worker lifespans.
"""
import os
import sys
import logging
import asyncio
import re
import tempfile
import zipfile
import shutil
import hashlib
from arq.connections import RedisSettings
import grpc
import redis.asyncio as aioredis

from shared.proto_gen import ai_pb2
from shared.utils.minio import get_minio, upload_bytes
from app.grpc_handlers.compilation_handler import extract_classes_from_dataset

logger = logging.getLogger(__name__)
"""Logger instance specific to background worker processes."""

async def _notify_compilation(ctx: dict, model_id: str, status: str, compiled_key: str,
                              compiled_sha256: str, hardware_type: str, error: str) -> None:
    """Invokes registry service update_compiled gRPC method to publish task progress.

    Args:
        ctx: Worker connection context state mapping.
        model_id: Target model UUID string.
        status: Compilation status tag string.
        compiled_key: MinIO target key containing output file.
        compiled_sha256: Hash validation tag string.
        hardware_type: Compilation target platform type.
        error: Descriptive error message string.
    """
    await ctx["ai_stub"].UpdateModelCompiled(ai_pb2.UpdateModelCompiledRequest(
        id=model_id, compiled_key=compiled_key, compiled_sha256=compiled_sha256,
        hardware_type=hardware_type, compile_status=status, compile_error=error,
    ))

async def check_cancellation(redis: aioredis.Redis, cancel_key: str, process: asyncio.subprocess.Process) -> None:
    """Monitors Redis cancellation keys and terminates subprocesses if cancel request triggers.

    Args:
        redis: Shared Redis async client instance.
        cancel_key: The Redis cancellation trigger key string.
        process: Subprocess handler to terminate.
    """
    try:
        while True:
            if await redis.exists(cancel_key):
                logger.info(f"Cancellation requested for {cancel_key}. Terminating subprocess...")
                try:
                    process.terminate()
                    await asyncio.sleep(1)
                    process.kill()
                except ProcessLookupError:
                    pass
                break
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        pass

async def train_job(
    ctx: dict,
    *,
    model_id: str,
    name: str,
    dataset_id: str,
    dataset_key: str,
    base_architecture: str,
    epochs: int,
    input_size: str,
    gpu_percent: float,
    device: str
) -> None:
    """Executes a YOLO model training task as a background worker.

    Downloads dataset ZIP from MinIO, invokes `yolo_train` script, parses
    log states, streams real-time training progress to Redis pubsub channels,
    retrieves output best.pt model weights, and uploads to MinIO.

    Args:
        ctx: Context mapping shared client references.
        model_id: Model database UUID.
        name: Run name prefix identifier.
        dataset_id: Source dataset UUID.
        dataset_key: ZIP object path key in MinIO.
        base_architecture: Weights file configuration.
        epochs: Epoch quantity.
        input_size: Training dimensions size.
        gpu_percent: Limits of GPU memory limits.
        device: CPU or target GPU index value.
    """
    logger.info(f"[train_job] Starting training run for model {model_id}...")
    redis = ctx.get("redis")
    cancel_key = f"cancel:train:{model_id}"
    if redis:
        await redis.delete(cancel_key)

    tmpdir = tempfile.mkdtemp()
    try:
        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        zip_path = os.path.join(tmpdir, "dataset.zip")
        extract_dir = os.path.join(tmpdir, "dataset")
        os.makedirs(extract_dir, exist_ok=True)

        logger.info(f"[train_job] Downloading dataset datasets/{dataset_key} to {zip_path}...")
        minio = get_minio()
        await minio.fget_object("datasets", dataset_key, zip_path)

        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        logger.info(f"[train_job] Extracting dataset to {extract_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        base_model_path = os.path.join(tmpdir, "base_model.pt")
        try:
            if "/" in base_architecture:
                logger.info(f"[train_job] Checking models bucket for custom weights: {base_architecture}...")
                await minio.fget_object("models", base_architecture, base_model_path)
                logger.info(f"[train_job] Downloaded custom base weights {base_architecture} from MinIO models bucket.")
            else:
                logger.info(f"[train_job] Checking base-models bucket for {base_architecture}...")
                await minio.fget_object("base-models", base_architecture, base_model_path)
                if os.path.exists(base_model_path) and os.path.getsize(base_model_path) == 0:
                    logger.info(f"[train_job] Base model {base_architecture} in MinIO is a 0-byte placeholder. Ignoring.")
                    try:
                        os.remove(base_model_path)
                    except Exception:
                        pass
                    raise FileNotFoundError("Placeholder 0-byte model file")
                logger.info(f"[train_job] Downloaded base model {base_architecture} from MinIO.")
        except Exception as e:
            logger.info(f"[train_job] Base model {base_architecture} not in MinIO or is placeholder: {e}. YOLO will auto-download.")
            base_model_path = base_architecture

        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        cmd = [
            sys.executable,
            "-u",
            "-m", "app.compilers.yolo_train",
            "--data_dir", extract_dir,
            "--init_model", base_model_path,
            "--epochs", str(epochs),
            "--device", str(device),
            "--gpu_percent", str(gpu_percent),
            "--image_size", input_size,
            "--name", name
        ]

        logger.info(f"[train_job] Executing training command: {' '.join(cmd)}")
        
        sub_env = os.environ.copy()
        sub_env["PYTHONUNBUFFERED"] = "1"

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd="/app",
            env=sub_env,
            limit=1024 * 1024 * 10
        )
        
        cancellation_task = None
        if redis:
            cancellation_task = asyncio.create_task(
                check_cancellation(redis, cancel_key, process)
            )

        redis_channel = f"train_logs:{model_id}"
        redis_list = f"train_logs:{model_id}_list"
        
        if redis:
            await redis.delete(redis_list)

        output_buffer = []
        raw_buffer = b""
        try:
            while True:
                chunk = await process.stdout.read(8192)
                if not chunk:
                    break

                raw_buffer += chunk

                lines_raw = []
                while raw_buffer:
                    r_pos = raw_buffer.find(b'\r')
                    n_pos = raw_buffer.find(b'\n')

                    if r_pos == -1 and n_pos == -1:
                        break

                    if r_pos == -1:
                        pos = n_pos
                    elif n_pos == -1:
                        pos = r_pos
                    else:
                        pos = min(r_pos, n_pos)

                    line_bytes = raw_buffer[:pos]
                    if pos + 1 < len(raw_buffer) and raw_buffer[pos:pos+2] == b'\r\n':
                        raw_buffer = raw_buffer[pos+2:]
                    else:
                        raw_buffer = raw_buffer[pos+1:]

                    if line_bytes.strip():
                        lines_raw.append(line_bytes)

                for line_bytes in lines_raw:
                    try:
                        line_str = line_bytes.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        line_str = line_bytes.decode('utf-8', errors='replace').strip()

                    if not line_str:
                        continue

                    output_buffer.append(line_str)

                    progress_match = re.search(r'(\d+)%\|', line_str)
                    if progress_match:
                        pct = int(progress_match.group(1))
                        if pct % 5 != 0:
                            continue

                    if redis:
                        try:
                            await redis.rpush(redis_list, line_str)
                            await redis.ltrim(redis_list, -5000, -1)
                            await redis.expire(redis_list, 86400)
                            await redis.publish(redis_channel, line_str)
                        except Exception as e:
                            logger.warning(f"Failed to publish log to redis: {e}")

            if raw_buffer.strip():
                try:
                    line_str = raw_buffer.decode('utf-8', errors='replace').strip()
                except Exception:
                    line_str = str(raw_buffer)
                if line_str:
                    output_buffer.append(line_str)
                    if redis:
                        try:
                            await redis.rpush(redis_list, line_str)
                            await redis.publish(redis_channel, line_str)
                        except Exception:
                            pass

            await process.wait()
        finally:
            if cancellation_task:
                cancellation_task.cancel()
                try:
                    await cancellation_task
                except asyncio.CancelledError:
                    pass

        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        if process.returncode != 0:
            err_content = "\n".join(output_buffer[-50:])
            logger.error(f"[train_job] YOLO training subprocess failed:\n{err_content}")
            raise RuntimeError(f"YOLO training failed (exit code {process.returncode}):\n{err_content}")

        logger.info("[train_job] Training subprocess complete. Locating best.pt weights...")

        best_weights_path = f"/app/run/{name}/weights/best.pt"
        if not os.path.exists(best_weights_path):
            import glob
            search_pattern = f"/app/run/**/{name}/**/best.pt"
            found_files = glob.glob(search_pattern, recursive=True)
            if found_files:
                best_weights_path = found_files[0]
            else:
                found_files = glob.glob("/app/run/**/best.pt", recursive=True) + glob.glob("/app/runs/**/best.pt", recursive=True)
                if found_files:
                    best_weights_path = found_files[0]
                else:
                    raise FileNotFoundError(f"Could not locate best.pt weights in run/ or runs/ directory.")

        logger.info(f"[train_job] Found best.pt at {best_weights_path}. Reading weights...")
        
        with open(best_weights_path, "rb") as f:
            data = f.read()
        
        sha = hashlib.sha256(data).hexdigest()
        model_key = f"{model_id}/model.pt"

        logger.info(f"[train_job] Uploading trained model to MinIO: models/{model_key}...")
        await upload_bytes("models", model_key, data)

        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        await ctx["ai_stub"].UpdateModelCompiled(ai_pb2.UpdateModelCompiledRequest(
            id=model_id,
            compiled_key="",
            compiled_sha256="",
            hardware_type="",
            compile_status="ready",
            compile_error="",
            source_key=model_key,
            source_sha256=sha
        ))

        logger.info(f"[train_job] Model {model_id} training complete and registered successfully.")
        
        if redis:
            await redis.set(f"model_train_done:{model_id}", "ready", ex=86400)

    except asyncio.CancelledError:
        logger.info(f"Training job {model_id} was cancelled by user.")
        try:
            await _notify_compilation(ctx, model_id, "failed", "", "", "", "Training cancelled by user")
        except Exception:
            pass
        if redis:
            await redis.set(f"model_train_done:{model_id}", "failed:Training cancelled by user", ex=86400)
            await redis.delete(cancel_key)
    except Exception as e:
        logger.exception(f"[train_job] Training error for model {model_id}")
        await _notify_compilation(ctx, model_id, "failed", "", "", "", str(e))
        if redis:
            await redis.set(f"model_train_done:{model_id}", f"failed:{str(e)}", ex=86400)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

async def compile_job(
    ctx: dict,
    *,
    model_id: str,
    source_key: str,
    hardware_type: str,
    num_classes: int,
    class_names: list[str],
    dataset_id: str,
    dataset_key: str,
    base_architecture: str,
    input_size: str
) -> None:
    """Executes a model compilation task as a background worker.

    Finds the matching target Compiler class, calls its compile pipeline, and
    saves progress updates to registry servers and Redis databases.

    Args:
        ctx: Shared worker connection references.
        model_id: Target model UUID string.
        source_key: Raw source weights key in MinIO.
        hardware_type: Compilation target platform type string.
        num_classes: Total class count.
        class_names: Class labels list.
        dataset_id: Source dataset UUID.
        dataset_key: Dataset archive key in MinIO.
        base_architecture: Parent model configuration.
        input_size: Tensor dimensions.
    """
    logger.info(f"[compile_job] Starting compilation for model {model_id} (hw: {hardware_type})...")
    redis = ctx.get("redis")
    cancel_key = f"cancel:compile:{model_id}"
    if redis:
        await redis.delete(cancel_key)
        await redis.delete(f"model_compile_done:{model_id}")
        await redis.delete(f"train_logs:{model_id}_list")
        await redis.rpush(f"train_logs:{model_id}_list", f"[Compiler] Iniciando proceso de compilación para target={hardware_type}...")
        await redis.publish(f"train_logs:{model_id}", f"[Compiler] Iniciando proceso de compilación para target={hardware_type}...")

    from app.config import get_settings
    from app.compilers import discover_compilers
    s = get_settings()
    compiler_registry = discover_compilers(s.minio_bucket_models, s.minio_bucket_compiled)
    if redis:
        for comp in compiler_registry.values():
            comp.redis_client = redis

    compiler = compiler_registry.get(hardware_type)
    if compiler is None:
        error_msg = f"No compiler for hardware: {hardware_type}"
        await _notify_compilation(ctx, model_id, "failed", "", "", hardware_type, error_msg)
        if redis:
            await redis.set(f"model_compile_done:{model_id}", f"failed:{error_msg}", ex=86400)
        return

    try:
        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        if not class_names and dataset_key:
            try:
                if redis:
                    await redis.rpush(f"train_logs:{model_id}_list", "[Compiler] Extrayendo clases del dataset...")
                    await redis.publish(f"train_logs:{model_id}", "[Compiler] Extrayendo clases del dataset...")
                class_names = await extract_classes_from_dataset("datasets", dataset_key)
                num_classes = len(class_names)
                logger.info(f"Extracted {num_classes} classes from dataset zip: {class_names}")
            except Exception as e:
                logger.error(f"Failed to extract classes from dataset zip: {e}")

        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        result = await compiler.compile(
            model_id=model_id,
            source_key=source_key,
            num_classes=num_classes,
            class_names=class_names,
            hardware_type=hardware_type,
            dataset_id=dataset_id,
            dataset_key=dataset_key,
            base_architecture=base_architecture,
            input_size=input_size,
        )

        if redis and await redis.exists(cancel_key):
            raise asyncio.CancelledError()

        if result.success:
            await _notify_compilation(ctx, model_id, "ready", result.compiled_key,
                                     result.compiled_sha256, hardware_type, "")
            logger.info(f"Compilation OK: {model_id}")
            if redis:
                await redis.set(f"model_compile_done:{model_id}", "ready", ex=86400)
        else:
            await _notify_compilation(ctx, model_id, "failed", "", "", hardware_type, result.error)
            logger.error(f"Compilation failed: {model_id} — {result.error}")
            if redis:
                await redis.set(f"model_compile_done:{model_id}", f"failed:{result.error}", ex=86400)

    except asyncio.CancelledError:
        logger.info(f"Compilation job {model_id} was cancelled by user.")
        try:
            await _notify_compilation(ctx, model_id, "failed", "", "", hardware_type, "Compilation cancelled by user")
        except Exception:
            pass
        if redis:
            await redis.set(f"model_compile_done:{model_id}", "failed:Compilation cancelled by user", ex=86400)
            await redis.delete(cancel_key)
    except Exception as e:
        logger.exception(f"Unexpected compilation error for {model_id}")
        await _notify_compilation(ctx, model_id, "failed", "", "", hardware_type, str(e))
        if redis:
            await redis.set(f"model_compile_done:{model_id}", f"failed:{str(e)}", ex=86400)

class WorkerSettings:
    """ARQ Worker configuration class defining tasks and lifecycle hooks."""
    
    functions = [train_job, compile_job]
    """List of registered execution tasks."""
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    """Redis settings derived from environment variables."""
    queue_name = "mlops_queue"
    """Name of the worker broker queue."""
    max_jobs = 1
    """Maximum concurrent runs allowed on this worker process."""
    job_timeout = 7200
    """Duration threshold in seconds before a task is forced to terminate."""
    keep_result = 3600
    """Duration in seconds to preserve the task result definition in Redis."""

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        """Connects gRPC, MinIO, and Redis client singletons at worker process startup.

        Args:
            ctx: Shared connection dictionary context.
        """
        from app.config import get_settings
        from app.compilers import discover_compilers
        from shared.utils.minio import init_minio, ensure_buckets
        from shared.proto_gen import ai_pb2_grpc
        import grpc
        import redis.asyncio as aioredis

        s = get_settings()
        init_minio(s.minio_endpoint, s.minio_access_key, s.minio_secret_key,
                   s.minio_secure, {"models": s.minio_bucket_models,
                                    "compiled": s.minio_bucket_compiled,
                                    "datasets": "datasets"})
        await ensure_buckets()

        ai_channel = grpc.aio.insecure_channel(s.ai_service_grpc)
        ctx["ai_stub"] = ai_pb2_grpc.AIServiceStub(ai_channel)
        ctx["ai_channel"] = ai_channel

        redis_client = aioredis.from_url(s.redis_url)
        ctx["redis"] = redis_client

    @staticmethod
    async def on_shutdown(ctx: dict) -> None:
        """Closes gRPC and Redis connection pool clients at worker process shutdown.

        Args:
            ctx: Shared connection dictionary context.
        """
        if "ai_channel" in ctx:
            await ctx["ai_channel"].close()
        if "redis" in ctx:
            await ctx["redis"].close()
