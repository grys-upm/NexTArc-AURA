"""gRPC service handler orchestrating training and hardware compilation pipelines.

Handles enqueuing of background task workers to compile YOLOv8 models or train
on raw datasets, reporting build metrics to the database registry.
"""
import asyncio
import logging
import os
import tempfile
import zipfile
import json

import grpc
from arq import create_pool
from arq.connections import RedisSettings
from shared.proto_gen import compilation_pb2, compilation_pb2_grpc, ai_pb2, ai_pb2_grpc
from app.compilers import discover_compilers
from app.compilers.base import CompilerBase, CompilationResult
from shared.utils.minio import get_minio

logger = logging.getLogger(__name__)
"""Logger instance specific to compilation handlers."""

async def extract_classes_from_dataset(bucket: str, dataset_key: str) -> list[str]:
    """Downloads a dataset ZIP and extracts class names ordered by index from classes.json.

    Args:
        bucket: MinIO dataset bucket.
        dataset_key: Dataset ZIP path object key.

    Returns:
        Sorted class labels names list.

    Raises:
        ValueError: If zip extraction or classes format parses incorrectly.
    """
    if not dataset_key:
        return []
    minio = get_minio()
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "dataset.zip")
        await minio.fget_object(bucket, dataset_key, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            classes_file = None
            for name in zip_ref.namelist():
                if name.endswith("classes.json"):
                    classes_file = name
                    break
            if not classes_file:
                raise ValueError("classes.json not found in dataset zip")
            with zip_ref.open(classes_file) as f:
                classes_data = json.load(f)
            
            if isinstance(classes_data, list):
                return [str(x) for x in classes_data]
            elif isinstance(classes_data, dict):
                try:
                    # Format A: {"0": "alert", "1": "drowsy"} (index -> name)
                    first_key = next(iter(classes_data.keys()))
                    int(first_key)
                    sorted_keys = sorted(classes_data.keys(), key=lambda k: int(k))
                    return [str(classes_data[k]) for k in sorted_keys]
                except (ValueError, TypeError):
                    try:
                        # Format B: {"alert": 0, "drowsy": 1} (name -> index)
                        sorted_keys = sorted(classes_data.keys(), key=lambda k: int(classes_data[k]))
                        return [str(k) for k in sorted_keys]
                    except (ValueError, TypeError):
                        return sorted([str(k) for k in classes_data.keys()])
            else:
                raise ValueError("'classes.json' must be a JSON list or dictionary.")

def _build_registry(minio_bucket_models: str, minio_bucket_compiled: str) -> dict:
    """Builds and returns the supported target hardware compilers registry dictionary.

    Args:
        minio_bucket_models: MinIO source bucket.
        minio_bucket_compiled: MinIO destination bucket.

    Returns:
        Registry mapping hardware target strings to CompilerBase subclasses.
    """
    return discover_compilers(minio_bucket_models, minio_bucket_compiled)

class CompilationServiceHandler(compilation_pb2_grpc.CompilationServiceServicer):
    """gRPC Service Servicer implementing model compilation and training workflows."""

    def __init__(self, ai_service_grpc: str, minio_bucket_models: str,
                 minio_bucket_compiled: str, redis_url: str):
        """Initializes the Compilation Service Handler and connects client channels.

        Args:
            ai_service_grpc: Registry service endpoint address.
            minio_bucket_models: Source bucket.
            minio_bucket_compiled: Destination bucket.
            redis_url: Task broker Redis settings connection string.
        """
        self._ai_channel = grpc.aio.insecure_channel(ai_service_grpc)
        self._ai_stub = ai_pb2_grpc.AIServiceStub(self._ai_channel)
        self._minio_bucket_models = minio_bucket_models
        self._minio_bucket_compiled = minio_bucket_compiled
        self._redis_settings = RedisSettings.from_dsn(redis_url)
        self._redis_pool = None

    async def _get_pool(self) -> any:
        """Retrieves or creates the shared Redis connection pool instance.

        Returns:
            ARQ Redis connection pool.
        """
        if self._redis_pool is None:
            self._redis_pool = await create_pool(self._redis_settings, default_queue_name="mlops_queue")
        return self._redis_pool

    async def CompileModel(
        self, req: compilation_pb2.CompileModelRequest, ctx: grpc.aio.ServicerContext
    ) -> compilation_pb2.CompileModelResponse:
        """Enqueues a background compilation job for a specific target hardware.

        Args:
            req: Model compilation details request.
            ctx: gRPC connection context.

        Returns:
            CompileModelResponse indicating initial enqueued status.
        """
        logger.info(f"CompileModel: model_id={req.model_id} hw={req.hardware_type}")
        dataset_key = (req.dataset_key or "").strip()

        registry = _build_registry(self._minio_bucket_models, self._minio_bucket_compiled)
        compiler = registry.get(req.hardware_type)
        if compiler is None:
            await self._notify(req.model_id, "failed", "", "", req.hardware_type,
                               f"No compiler for hardware: {req.hardware_type}")
            return compilation_pb2.CompileModelResponse(
                model_id=req.model_id, status="failed",
                error=f"No compiler implemented for: {req.hardware_type}")

        await self._notify(req.model_id, "compiling", "", "", req.hardware_type, "")

        pool = await self._get_pool()
        await pool.delete(f"arq:job:compile:{req.model_id}")
        await pool.delete(f"arq:result:compile:{req.model_id}")

        await pool.enqueue_job(
            "compile_job",
            model_id=req.model_id,
            source_key=req.source_key,
            hardware_type=req.hardware_type,
            num_classes=req.num_classes,
            class_names=list(req.class_names),
            dataset_id=req.dataset_id or "",
            dataset_key=dataset_key,
            base_architecture=req.base_architecture or "",
            input_size=req.input_size or "",
            _job_id=f"compile:{req.model_id}",
        )
        logger.info(f"compile_job enqueued for model {req.model_id}")

        return compilation_pb2.CompileModelResponse(
            model_id=req.model_id, status="compiling")

    async def TrainModel(
        self, req: compilation_pb2.TrainModelRequest, ctx: grpc.aio.ServicerContext
    ) -> compilation_pb2.TrainModelResponse:
        """Enqueues a background training task to optimize YOLO models.

        Args:
            req: Model training request details.
            ctx: gRPC connection context.

        Returns:
            TrainModelResponse indicating enqueued status.
        """
        logger.info(f"TrainModel: model_id={req.model_id}")
        dataset_key = (req.dataset_key or "").strip()

        if not dataset_key:
            msg = "Dataset key is required for training"
            await self._notify(req.model_id, "failed", "", "", "", msg)
            return compilation_pb2.TrainModelResponse(model_id=req.model_id, status="failed")

        await self._notify(req.model_id, "training", "", "", "", "")

        pool = await self._get_pool()
        await pool.delete(f"arq:job:train:{req.model_id}")
        await pool.delete(f"arq:result:train:{req.model_id}")

        await pool.enqueue_job(
            "train_job",
            model_id=req.model_id,
            name=req.name,
            dataset_id=req.dataset_id,
            dataset_key=dataset_key,
            base_architecture=req.base_architecture or "yolov8n.pt",
            epochs=req.epochs or 20,
            input_size=req.input_size or "640x640",
            gpu_percent=req.gpu_percent or 0.9,
            device=req.device or "0",
            _job_id=f"train:{req.model_id}",
        )
        logger.info(f"train_job enqueued for model {req.model_id}")

        return compilation_pb2.TrainModelResponse(model_id=req.model_id, status="training")

    async def GetCompilationStatus(
        self, req: compilation_pb2.GetCompilationStatusRequest, ctx: grpc.aio.ServicerContext
    ) -> compilation_pb2.CompileModelResponse:
        """Checks the current build database status of a model.

        Args:
            req: Model status check request.
            ctx: gRPC connection context.

        Returns:
            CompileModelResponse carrying compilation status.
        """
        model = await self._ai_stub.GetModel(ai_pb2.GetModelRequest(id=req.model_id))
        return compilation_pb2.CompileModelResponse(
            model_id=model.id,
            status=model.compile_status,
            compiled_key=model.compiled_key,
            compiled_sha256=model.compiled_sha256,
            error=model.compile_error,
        )

    async def GetSupportedHardware(
        self, req: compilation_pb2.GetSupportedHardwareRequest, ctx: grpc.aio.ServicerContext
    ) -> compilation_pb2.GetSupportedHardwareResponse:
        """Lists compile hardware capabilities descriptions.

        Args:
            req: Empty query message.
            ctx: gRPC connection context.

        Returns:
            GetSupportedHardwareResponse message.
        """
        from app.compilers import get_architectures_data
        archs_data = get_architectures_data()
        return compilation_pb2.GetSupportedHardwareResponse(
            hardware_types=sorted(list(archs_data.keys())),
            labels=archs_data
        )

    async def GetSupportedSensors(
        self, req: compilation_pb2.GetSupportedSensorsRequest, ctx: grpc.aio.ServicerContext
    ) -> compilation_pb2.GetSupportedSensorsResponse:
        """Lists supported sensor library names.

        Args:
            req: Empty query message.
            ctx: gRPC connection context.

        Returns:
            GetSupportedSensorsResponse message.
        """
        from app.sensors import get_sensors_data, get_sensors
        sensors_data = get_sensors_data()
        return compilation_pb2.GetSupportedSensorsResponse(
            sensors=get_sensors(),
            labels=sensors_data
        )

    async def GetSupportedActuators(
        self, req: compilation_pb2.GetSupportedActuatorsRequest, ctx: grpc.aio.ServicerContext
    ) -> compilation_pb2.GetSupportedActuatorsResponse:
        """Lists supported actuator library names.

        Args:
            req: Empty query message.
            ctx: gRPC connection context.

        Returns:
            GetSupportedActuatorsResponse message.
        """
        from app.actuators import get_actuators_data, get_actuators
        actuators_data = get_actuators_data()
        return compilation_pb2.GetSupportedActuatorsResponse(
            actuators=get_actuators(),
            labels=actuators_data
        )

    async def GetSupportedOthers(
        self, req: compilation_pb2.GetSupportedOthersRequest, ctx: grpc.aio.ServicerContext
    ) -> compilation_pb2.GetSupportedOthersResponse:
        """Lists other support drivers names.

        Args:
            req: Empty query message.
            ctx: gRPC connection context.

        Returns:
            GetSupportedOthersResponse message.
        """
        from app.others import get_others_data, get_others
        others_data = get_others_data()
        return compilation_pb2.GetSupportedOthersResponse(
            others=get_others(),
            labels=others_data
        )

    async def _notify(self, model_id: str, status: str, compiled_key: str,
                      compiled_sha256: str, hardware_type: str, error: str) -> None:
        """Pushes updated build results to the central registry service.

        Args:
            model_id: Target model ID.
            status: New build status.
            compiled_key: Output compiled key.
            compiled_sha256: Output compiled checksum.
            hardware_type: Compilation target type.
            error: Output build error description.
        """
        await self._ai_stub.UpdateModelCompiled(ai_pb2.UpdateModelCompiledRequest(
            id=model_id, compiled_key=compiled_key, compiled_sha256=compiled_sha256,
            hardware_type=hardware_type, compile_status=status, compile_error=error,
        ))
