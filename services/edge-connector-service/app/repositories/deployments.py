"""Repository module wrapping database operations for Deployment and mirror entity records."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import Deployment, DeviceRef, ModelRef, ScriptRef

class DeploymentRepository:
    """Provides SQL access query handlers wrapping Deployment and mirror database objects."""

    def __init__(self, s: AsyncSession):
        """Initializes the DeploymentRepository.

        Args:
            s: SQLAlchemy async database session.
        """
        self.s = s

    async def create(
        self, device_id: str, model_id: str, script_id: str,
        name: str | None = None, status: str = "pending"
    ) -> Deployment:
        """Saves a new OTA deployment job details in the database.

        Args:
            device_id: Target edge device UUID string.
            model_id: Compiled model UUID string.
            script_id: Custom script UUID string.
            name: Optional display name for the job.
            status: Progress state of the deployment.

        Returns:
            The created Deployment model instance.
        """
        d = Deployment(device_id=device_id, model_id=model_id, script_id=script_id, name=name, status=status)
        self.s.add(d)
        await self.s.commit()
        await self.s.refresh(d)
        return d

    async def get(self, id: str) -> Deployment | None:
        """Retrieves a single deployment by its UUID primary key.

        Args:
            id: Target deployment ID.

        Returns:
            Deployment database object or None if not found.
        """
        return await self.s.get(Deployment, id)

    async def list_all(self) -> list[Deployment]:
        """Lists all deployments ordered by created timestamp descending.

        Returns:
            List of registered deployments.
        """
        r = await self.s.execute(select(Deployment).order_by(Deployment.created_at.desc()))
        return list(r.scalars().all())

    async def list_for_device(self, device_id: str) -> list[Deployment]:
        """Lists all OTA deployments mapped to a specific device.

        Args:
            device_id: Target device identifier.

        Returns:
            List of deployments.
        """
        r = await self.s.execute(
            select(Deployment).where(Deployment.device_id == device_id)
            .order_by(Deployment.created_at.desc()))
        return list(r.scalars().all())

    async def mark_sent(self, d: Deployment) -> None:
        """Updates deployment status to 'sent' and sets timestamp.

        Args:
            d: The deployment entity instance.
        """
        d.status = "sent"
        d.sent_at = datetime.now(timezone.utc)
        await self.s.commit()

    async def mark_running(self, d: Deployment) -> None:
        """Activates a deployment run, marking all older active runs as 'stopped'.

        Args:
            d: The deployment entity instance.
        """
        from sqlalchemy import update
        await self.s.execute(
            update(Deployment)
            .where(
                Deployment.device_id == d.device_id,
                Deployment.id != d.id,
                Deployment.status.in_(["running", "sent", "pending", "compiling"])
            )
            .values(status="stopped")
        )
        d.status = "running"
        d.running_at = datetime.now(timezone.utc)
        await self.s.commit()

    async def mark_failed(self, d: Deployment, error: str) -> None:
        """Marks a deployment status as 'failed' and saves the error message.

        Args:
            d: The deployment entity instance.
            error: The error message string.
        """
        d.status = "failed"
        d.error_msg = error
        await self.s.commit()

    async def get_device(self, id: str) -> DeviceRef | None:
        """Retrieves mirror DeviceRef entity by ID.

        Args:
            id: Target device ID.

        Returns:
            DeviceRef object or None if not found.
        """
        return await self.s.get(DeviceRef, id)

    async def get_model(self, id: str) -> ModelRef | None:
        """Retrieves mirror ModelRef entity by ID.

        Args:
            id: Target model ID.

        Returns:
            ModelRef object or None if not found.
        """
        return await self.s.get(ModelRef, id)

    async def get_script(self, id: str) -> ScriptRef | None:
        """Retrieves mirror ScriptRef entity by ID.

        Args:
            id: Target script ID.

        Returns:
            ScriptRef object or None if not found.
        """
        return await self.s.get(ScriptRef, id)
