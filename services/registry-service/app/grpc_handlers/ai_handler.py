"""Registry Service gRPC handler for managing ML models and datasets metadata.

Handles registration of training/uploaded models, dataset files version tracking,
and association records within PostgreSQL database sessions.
"""
import grpc
import json
from sqlalchemy.ext.asyncio import async_sessionmaker
from shared.proto_gen import ai_pb2, ai_pb2_grpc
from app.repositories.models import DatasetRepository, ModelRepository

ALLOWED_BASE_MODELS = {
    "yolov10b.pt", "yolov10n.pt", "yolov10s.pt", "yolov10x.pt",
    "yolov11l.pt", "yolov11m.pt", "yolov11n.pt", "yolov11s.pt", "yolov11x.pt",
    "yolov3_416.pt", "yolov3_gluon_416.pt", "yolov3_gluon.pt", "yolov3.pt",
    "yolov4_leaky.pt", "yolov5m_6.1.pt", "yolov5m6_6.1.pt",
    "yolov5m_vehicles_nv12.pt", "yolov5m_vehicles.pt", "yolov5m_vehicles_yuy2.pt",
    "yolov5m_wo_spp.pt", "yolov5m_wo_spp_yuy2.pt", "yolov5m.pt",
    "yolov5s_bbox_decoding_only.pt", "yolov5s_c3tr.pt", "yolov5s_personface_nv12.pt",
    "yolov5s_personface_rgbx.pt", "yolov5s_personface.pt", "yolov5s_wo_spp.pt",
    "yolov5s.pt", "yolov5xs_wo_spp_nms_core.pt", "yolov5xs_wo_spp.pt",
    "yolov6n_0.2.1_nms_core.pt", "yolov6n_0.2.1.pt", "yolov6n.pt",
    "yolov7e6.pt", "yolov7_tiny.pt", "yolov7.pt", "yolov8l.pt",
    "yolov8m.pt", "yolov8n.pt", "yolov8s_bbox_decoding_only.pt",
    "yolov8s.pt", "yolov8x.pt", "yolov9c.pt",
    "yolox_l_leaky.pt", "yolox_s_leaky.pt", "yolox_s_wide_leaky.pt",
    "yolox_tiny.pt"
}
"""Set of pre-compiled or pre-trained baseline model weights filename options."""

def _to_proto(m) -> ai_pb2.ModelResponse:
    """Formats an ORM Model record to its corresponding Protobuf message type.

    Args:
        m: The ORM Model entity instance.

    Returns:
        The populated ModelResponse Protobuf object.
    """
    compilations_proto = []
    if "compilations" in m.__dict__ and m.compilations:
        for c in m.compilations:
            compilations_proto.append(ai_pb2.ModelCompilationResponse(
                id=c.id,
                model_id=c.model_id,
                hardware_type=c.hardware_type,
                compiled_key=c.compiled_key or "",
                compiled_sha256=c.compiled_sha256 or "",
                compile_status=c.compile_status,
                compile_error=c.compile_error or "",
                created_at=c.created_at.isoformat() if c.created_at else ""
            ))

    return ai_pb2.ModelResponse(
        id=m.id, name=m.name, description=m.description or "",
        source_key=m.source_key, source_sha256=m.source_sha256,
        compiled_key=m.compiled_key or "", compiled_sha256=m.compiled_sha256 or "",
        hardware_type=m.hardware_type or "", compile_status=m.compile_status,
        compile_error=m.compile_error or "", created_at=m.created_at.isoformat(),
        dataset_id=m.dataset_id or "",
        base_architecture=m.base_architecture or "",
        epochs=m.epochs or 0,
        input_size=m.input_size or "",
        batch_size=m.batch_size or 0,
        dataset_version_id=m.dataset_version_id or "",
        compilations=compilations_proto,
    )

def _dataset_to_proto(d) -> ai_pb2.DatasetResponse:
    """Formats an ORM Dataset record to its corresponding Protobuf message type.

    Args:
        d: The ORM Dataset entity instance.

    Returns:
        The populated DatasetResponse Protobuf object.
    """
    metadata_str = ""
    if d.meta_info:
        try:
            metadata_str = json.dumps(d.meta_info)
        except Exception:
            pass

    versions_proto = []
    if "versions" in d.__dict__ and d.versions:
        for v in d.versions:
            v_meta_str = ""
            if v.meta_info:
                try:
                    v_meta_str = json.dumps(v.meta_info)
                except Exception:
                    pass
            versions_proto.append(ai_pb2.DatasetVersionResponse(
                id=v.id,
                dataset_id=v.dataset_id,
                version=v.version,
                description=v.description or "",
                object_key=v.object_key,
                sha256=v.sha256,
                size_bytes=v.size_bytes,
                metadata=v_meta_str,
                created_at=v.created_at.isoformat(),
            ))

    return ai_pb2.DatasetResponse(
        id=d.id,
        name=d.name,
        description=d.description or "",
        created_at=d.created_at.isoformat(),
        object_key=d.object_key or "",
        sha256=d.sha256 or "",
        size_bytes=d.size_bytes or 0,
        metadata=metadata_str,
        versions=versions_proto,
    )

class AIServiceHandler(ai_pb2_grpc.AIServiceServicer):
    """gRPC Service Servicer handling Model and Dataset catalog queries and modifications."""

    def __init__(self, sf: async_sessionmaker):
        """Initializes the AI Service Handler.

        Args:
            sf: Database async session maker class.
        """
        self._sf = sf

    async def UploadModel(self, req: ai_pb2.UploadModelRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.ModelResponse:
        """Registers a new model record in the database.

        Args:
            req: Protobuf model request fields.
            ctx: gRPC connection context.

        Returns:
            The created ModelResponse Protobuf object.
        """
        base_arch = req.base_architecture or None
        if not base_arch or not base_arch.strip():
            await ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, "base_architecture is required")
            return

        base_arch = base_arch.strip()
        if not base_arch.endswith(".pt"):
            base_arch += ".pt"

        if "/" not in base_arch:
            from shared.utils.minio import get_minio
            from app.config import get_settings
            s = get_settings()
            minio = get_minio()
            try:
                objects = await minio.list_objects(s.minio_bucket_base_models)
                allowed = {obj.object_name for obj in objects}
            except Exception:
                allowed = ALLOWED_BASE_MODELS

            if base_arch not in allowed:
                await ctx.abort(grpc.StatusCode.INVALID_ARGUMENT,
                                f"base_architecture '{base_arch}' is not in the allowed list")
                return

        async with self._sf() as s:
            try:
                m = await ModelRepository(s).create(
                    req.name,
                    req.description or None,
                    req.source_key,
                    req.source_sha256,
                    req.dataset_id or None,
                    base_architecture=base_arch,
                    epochs=req.epochs or None,
                    input_size=req.input_size or None,
                    batch_size=req.batch_size or None,
                    dataset_version_id=req.dataset_version_id or None,
                )
            except ValueError as e:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, str(e))
                return
            return _to_proto(m)

    async def GetModel(self, req: ai_pb2.GetModelRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.ModelResponse:
        """Fetches a single model details from the registry database.

        Args:
            req: Model request query key.
            ctx: gRPC connection context.

        Returns:
            ModelResponse details.
        """
        async with self._sf() as s:
            m = await ModelRepository(s).get(req.id)
            if not m:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Model not found")
                return
            return _to_proto(m)

    async def ListModels(self, req: ai_pb2.ListModelsRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.ListModelsResponse:
        """Lists all registered models in the registry database.

        Args:
            req: Empty query request message.
            ctx: gRPC connection context.

        Returns:
            ListModelsResponse message.
        """
        async with self._sf() as s:
            models = await ModelRepository(s).list_all()
            return ai_pb2.ListModelsResponse(models=[_to_proto(m) for m in models])

    async def DeleteModel(self, req: ai_pb2.DeleteModelRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.DeleteModelResponse:
        """Deletes a model record from the database.

        Args:
            req: Target model ID request.
            ctx: gRPC connection context.

        Returns:
            DeleteModelResponse indicator.
        """
        async with self._sf() as s:
            ok = await ModelRepository(s).delete(req.id)
            if not ok:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Model not found")
                return
            return ai_pb2.DeleteModelResponse(success=True)

    async def UpdateModelCompiled(self, req: ai_pb2.UpdateModelCompiledRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.ModelResponse:
        """Updates compilation output properties on a model registry.

        Args:
            req: Update parameters.
            ctx: gRPC connection context.

        Returns:
            Updated model response.
        """
        async with self._sf() as s:
            m = await ModelRepository(s).update_compiled(
                req.id, req.compiled_key, req.compiled_sha256,
                req.hardware_type, req.compile_status, req.compile_error,
                source_key=req.source_key or None,
                source_sha256=req.source_sha256 or None
            )
            if not m:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Model not found")
                return
            return _to_proto(m)

    async def UploadDataset(self, req: ai_pb2.UploadDatasetRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.DatasetResponse:
        """Registers a new dataset reference entry in the database.

        Args:
            req: Dataset details parameters.
            ctx: gRPC connection context.

        Returns:
            Created DatasetResponse details.
        """
        async with self._sf() as s:
            d = await DatasetRepository(s).create(req.name, req.description or None)
            return _dataset_to_proto(d)

    async def GetDataset(self, req: ai_pb2.GetDatasetRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.DatasetResponse:
        """Retrieves a single dataset record by its unique ID.

        Args:
            req: Dataset request query key.
            ctx: gRPC connection context.

        Returns:
            DatasetResponse details.
        """
        async with self._sf() as s:
            d = await DatasetRepository(s).get(req.id)
            if not d:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Dataset not found")
                return
            return _dataset_to_proto(d)

    async def ListDatasets(self, req: ai_pb2.ListDatasetsRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.ListDatasetsResponse:
        """Lists all registered datasets.

        Args:
            req: Empty query request message.
            ctx: gRPC connection context.

        Returns:
            ListDatasetsResponse message.
        """
        async with self._sf() as s:
            items = await DatasetRepository(s).list_all()
            return ai_pb2.ListDatasetsResponse(datasets=[_dataset_to_proto(d) for d in items])

    async def DeleteDataset(self, req: ai_pb2.DeleteDatasetRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.DeleteDatasetResponse:
        """Removes a dataset and its versions from the registry database.

        Args:
            req: Target dataset ID request.
            ctx: gRPC connection context.

        Returns:
            DeleteDatasetResponse indicator.
        """
        async with self._sf() as s:
            ok = await DatasetRepository(s).delete(req.id)
            if not ok:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Dataset not found")
                return
            return ai_pb2.DeleteDatasetResponse(success=True)

    async def SetDatasetFile(self, req: ai_pb2.SetDatasetFileRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.DatasetResponse:
        """Associates an uploaded ZIP archive file key and version details with a dataset.

        Args:
            req: Dataset file association details.
            ctx: gRPC connection context.

        Returns:
            DatasetResponse details.
        """
        metadata_dict = None
        if req.metadata:
            try:
                metadata_dict = json.loads(req.metadata)
            except Exception:
                pass
        async with self._sf() as s:
            d = await DatasetRepository(s).set_file(
                req.dataset_id,
                req.object_key,
                req.sha256,
                req.size_bytes,
                meta_info=metadata_dict,
                version=req.version or None,
                description=req.description or None,
            )
            if not d:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Dataset not found")
                return
            return _dataset_to_proto(d)

    async def AssociateModelDataset(self, req: ai_pb2.AssociateModelDatasetRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.ModelResponse:
        """Binds a dataset version reference to an existing model record.

        Args:
            req: Model and dataset association parameters.
            ctx: gRPC connection context.

        Returns:
            Updated ModelResponse details.
        """
        async with self._sf() as s:
            try:
                m = await ModelRepository(s).associate_dataset(
                    req.model_id, req.dataset_id, req.dataset_version_id or None
                )
            except ValueError as e:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, str(e))
                return
            if not m:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Model not found")
                return
            return _to_proto(m)

    async def UpdateModel(self, req: ai_pb2.UpdateModelRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.ModelResponse:
        """Updates standard configuration metadata properties on a model registry.

        Args:
            req: Model parameter update fields.
            ctx: gRPC connection context.

        Returns:
            Updated ModelResponse details.
        """
        async with self._sf() as s:
            m = await ModelRepository(s).update(
                req.id,
                req.name,
                req.description or None,
                epochs=req.epochs if req.epochs > 0 else None,
                input_size=req.input_size or None,
                batch_size=req.batch_size if req.batch_size > 0 else None,
                base_architecture=req.base_architecture or None
            )
            if not m:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Model not found")
                return
            return _to_proto(m)

    async def UpdateDataset(self, req: ai_pb2.UpdateDatasetRequest, ctx: grpc.aio.ServicerContext) -> ai_pb2.DatasetResponse:
        """Updates catalog descriptions fields of a dataset record.

        Args:
            req: Dataset parameter update fields.
            ctx: gRPC connection context.

        Returns:
            Updated DatasetResponse details.
        """
        async with self._sf() as s:
            d = await DatasetRepository(s).update(
                req.id,
                req.name,
                req.description or None
            )
            if not d:
                await ctx.abort(grpc.StatusCode.NOT_FOUND, "Dataset not found")
                return
            return _dataset_to_proto(d)
