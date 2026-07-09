"""Repository module wrapping database operations for Model and Dataset records."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.orm import Dataset, Model, DatasetVersion

class ModelRepository:
    """Provides SQL access query handlers wrapping Model and ModelCompilation database objects."""

    def __init__(self, s: AsyncSession):
        """Initializes the ModelRepository.

        Args:
            s: SQLAlchemy async database session.
        """
        self.s = s

    async def create(
        self, name: str, description: str | None, source_key: str,
        source_sha256: str, dataset_id: str | None = None,
        base_architecture: str | None = None, epochs: int | None = None,
        input_size: str | None = None, batch_size: int | None = None,
        dataset_version_id: str | None = None
    ) -> Model:
        """Registers a new model and validates associated dataset keys.

        Args:
            name: Human-readable display label.
            description: Optional detailed comments.
            source_key: MinIO object key for raw input weights.
            source_sha256: SHA-256 hash checksum of source weights.
            dataset_id: Optional linked dataset UUID.
            base_architecture: Parent model configuration.
            epochs: Optional epoch count metadata.
            input_size: Optional WxH resolution.
            batch_size: Optional batch size parameter.
            dataset_version_id: Optional specific dataset version UUID.

        Returns:
            The created Model entity instance.

        Raises:
            ValueError: If dataset_id or dataset_version_id is invalid.
        """
        if dataset_id:
            d = await self.s.get(Dataset, dataset_id)
            if not d:
                raise ValueError("Dataset not found")
        if dataset_version_id:
            dv = await self.s.get(DatasetVersion, dataset_version_id)
            if not dv:
                raise ValueError("Dataset version not found")
        m = Model(
            name=name,
            description=description,
            source_key=source_key,
            source_sha256=source_sha256,
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            base_architecture=base_architecture,
            epochs=epochs,
            input_size=input_size,
            batch_size=batch_size,
        )
        self.s.add(m)
        await self.s.commit()
        return await self.get(m.id)

    async def get(self, id: str) -> Model | None:
        """Retrieves a single model database row including all compilations.

        Args:
            id: Target model UUID string.

        Returns:
            Model object or None if not found.
        """
        r = await self.s.execute(
            select(Model)
            .where(Model.id == id)
            .options(selectinload(Model.compilations))
        )
        return r.scalar_one_or_none()

    async def list_all(self) -> list[Model]:
        """Lists all registered models ordered by created timestamp descending.

        Returns:
            List of registered Model objects.
        """
        r = await self.s.execute(
            select(Model)
            .options(selectinload(Model.compilations))
            .order_by(Model.created_at.desc())
        )
        return list(r.scalars().all())

    async def update_compiled(
        self, id: str, compiled_key: str, compiled_sha256: str,
        hardware_type: str, compile_status: str, compile_error: str,
        source_key: str | None = None, source_sha256: str | None = None
    ) -> Model | None:
        """Updates compilation results and adds or updates target compiles.

        Args:
            id: Target model UUID.
            compiled_key: Compiled model MinIO object key.
            compiled_sha256: SHA-256 hash checksum of compiled binary.
            hardware_type: Compilation target platform architecture class.
            compile_status: The compilation execution status.
            compile_error: Error trace string if build failed.
            source_key: Optional updated source key.
            source_sha256: Optional updated source sha.

        Returns:
            Updated Model database object, or None if not found.
        """
        m = await self.get(id)
        if not m:
            return None

        if source_key:
            m.source_key = source_key
        if source_sha256:
            m.source_sha256 = source_sha256

        if hardware_type:
            if compile_status == "ready":
                m.compiled_key = compiled_key or None
                m.compiled_sha256 = compiled_sha256 or None
                m.hardware_type = hardware_type or None
                m.compile_status = "ready"
                m.compile_error = None
            else:
                if m.compile_status not in ("ready", "training"):
                    m.compile_status = "ready"

            from app.models.orm import ModelCompilation
            res = await self.s.execute(
                select(ModelCompilation)
                .where(ModelCompilation.model_id == id)
                .where(ModelCompilation.hardware_type == hardware_type)
            )
            comp = res.scalar_one_or_none()
            if not comp:
                comp = ModelCompilation(
                    model_id=id,
                    hardware_type=hardware_type,
                    compiled_key=compiled_key or "",
                    compiled_sha256=compiled_sha256 or "",
                    compile_status=compile_status,
                    compile_error=compile_error or None
                )
                self.s.add(comp)
            else:
                comp.compiled_key = compiled_key or ""
                comp.compiled_sha256 = compiled_sha256 or ""
                comp.compile_status = compile_status
                comp.compile_error = compile_error or None
        else:
            if compile_status:
                m.compile_status = compile_status
            if compile_error:
                m.compile_error = compile_error or None
            if compiled_key:
                m.compiled_key = compiled_key or None
            if compiled_sha256:
                m.compiled_sha256 = compiled_sha256 or None

        await self.s.commit()
        return await self.get(id)

    async def associate_dataset(self, model_id: str, dataset_id: str, dataset_version_id: str | None = None) -> Model | None:
        """Associates a dataset record and version with a registered model.

        Args:
            model_id: Target model UUID string.
            dataset_id: Target dataset UUID string.
            dataset_version_id: Optional target dataset version UUID string.

        Returns:
            Updated Model database object, or None if not found.

        Raises:
            ValueError: If dataset or dataset version does not exist.
        """
        m = await self.get(model_id)
        if not m:
            return None
        d = await self.s.get(Dataset, dataset_id)
        if not d:
            raise ValueError("Dataset not found")
        m.dataset_id = d.id
        if dataset_version_id:
            dv = await self.s.get(DatasetVersion, dataset_version_id)
            if not dv or dv.dataset_id != d.id:
                raise ValueError("Dataset version not found or does not belong to this dataset")
            m.dataset_version_id = dv.id
        else:
            m.dataset_version_id = None
        await self.s.commit()
        return await self.get(m.id)

    async def update(
        self, id: str, name: str, description: str | None,
        epochs: int | None = None, input_size: str | None = None,
        batch_size: int | None = None, base_architecture: str | None = None
    ) -> Model | None:
        """Updates standard configuration attributes on a model registry row.

        Args:
            id: Target model ID.
            name: New display name.
            description: New description comments.
            epochs: New training epochs count.
            input_size: New resolution size.
            batch_size: New batch size value.
            base_architecture: New base weights filename.

        Returns:
            Updated Model database object, or None if not found.
        """
        m = await self.get(id)
        if not m:
            return None
        m.name = name
        m.description = description
        if epochs is not None:
            m.epochs = epochs
        if input_size is not None:
            m.input_size = input_size
        if batch_size is not None:
            m.batch_size = batch_size
        if base_architecture is not None:
            m.base_architecture = base_architecture
        await self.s.commit()
        return await self.get(id)

    async def delete(self, id: str) -> bool:
        """Deletes a model record row from the registry database.

        Args:
            id: Target model ID.

        Returns:
            True if deletion was successful, False otherwise.
        """
        m = await self.get(id)
        if not m:
            return False
        await self.s.delete(m)
        await self.s.commit()
        return True


class DatasetRepository:
    """Provides SQL access query handlers wrapping Dataset database objects."""

    def __init__(self, s: AsyncSession):
        """Initializes the DatasetRepository.

        Args:
            s: SQLAlchemy async database session.
        """
        self.s = s

    async def create(self, name: str, description: str | None) -> Dataset:
        """Creates a new dataset catalog record.

        Args:
            name: Human-readable display label.
            description: Optional text comments details.

        Returns:
            The created Dataset database object.
        """
        d = Dataset(name=name, description=description)
        self.s.add(d)
        await self.s.commit()
        return await self.get(d.id)

    async def get(self, id: str) -> Dataset | None:
        """Retrieves a single dataset record including all associated versions.

        Args:
            id: Target dataset UUID string.

        Returns:
            Dataset object or None if not found.
        """
        r = await self.s.execute(
            select(Dataset)
            .where(Dataset.id == id)
            .options(selectinload(Dataset.versions))
        )
        return r.scalar_one_or_none()

    async def update(self, id: str, name: str, description: str | None) -> Dataset | None:
        """Updates name and description on a dataset record.

        Args:
            id: Target dataset UUID.
            name: New display name.
            description: Optional new description.

        Returns:
            Updated Dataset database object, or None if not found.
        """
        d = await self.get(id)
        if not d:
            return None
        d.name = name
        d.description = description
        await self.s.commit()
        return await self.get(id)

    async def set_file(
        self, dataset_id: str, object_key: str, sha256: str,
        size_bytes: int, meta_info: dict | None = None,
        version: str | None = None, description: str | None = None
    ) -> Dataset | None:
        """Creates and stores a new DatasetVersion row and links the parent dataset pointer to it.

        Args:
            dataset_id: Target dataset UUID.
            object_key: MinIO storage key.
            sha256: SHA-256 validation code.
            size_bytes: Size in bytes.
            meta_info: JSON dictionary metadata details.
            version: Optional version tag.
            description: Optional release notes.

        Returns:
            Updated parent Dataset object, or None if not found.
        """
        d = await self.s.get(Dataset, dataset_id)
        if not d:
            return None
        
        if not version or not version.strip():
            r = await self.s.execute(
                select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
            )
            existing_versions = r.scalars().all()
            version = f"v{len(existing_versions) + 1}"
            
        dv = DatasetVersion(
            dataset_id=dataset_id,
            version=version.strip(),
            description=description,
            object_key=object_key,
            sha256=sha256,
            size_bytes=size_bytes,
            meta_info=meta_info
        )
        self.s.add(dv)
        
        d.object_key = object_key
        d.sha256 = sha256
        d.size_bytes = size_bytes
        if meta_info is not None:
            d.meta_info = meta_info
            
        await self.s.commit()
        return await self.get(dataset_id)

    async def list_all(self) -> list[Dataset]:
        """Lists all datasets ordered by created timestamp descending.

        Returns:
            List of registered datasets.
        """
        r = await self.s.execute(
            select(Dataset)
            .options(selectinload(Dataset.versions))
            .order_by(Dataset.created_at.desc())
        )
        return list(r.scalars().all())

    async def delete(self, id: str) -> bool:
        """Deletes a dataset and all associated versions from the registry database.

        Args:
            id: Target dataset UUID.

        Returns:
            True if deletion was successful, False otherwise.
        """
        d = await self.get(id)
        if not d:
            return False
        await self.s.delete(d)
        await self.s.commit()
        return True
