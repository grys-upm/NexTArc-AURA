"""Repository module wrapping database operations for Device records."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import Device

class DeviceRepository:
    """Provides SQL access query handlers wrapping Device database objects."""

    def __init__(self, s: AsyncSession):
        """Initializes the DeviceRepository.

        Args:
            s: SQLAlchemy async database session.
        """
        self.s = s

    async def create(
        self, name: str, hardware_type: str, description: str | None,
        sensors: list[str], actuators: list[str], others: list[str]
    ) -> Device:
        """Saves a new device record details in the database.

        Args:
            name: Human-readable display label.
            hardware_type: Hardware target compiler class type.
            description: Optional text comments details.
            sensors: list of enabled sensor IDs.
            actuators: list of enabled actuator IDs.
            others: list of other peripheral IDs.

        Returns:
            The created Device model instance.
        """
        d = Device(name=name, hardware_type=hardware_type, description=description, sensors=sensors, actuators=actuators, others=others)
        self.s.add(d)
        await self.s.commit()
        await self.s.refresh(d)
        return d

    async def get(self, id: str) -> Device | None:
        """Retrieves a single device by its UUID primary key.

        Args:
            id: Target device ID.

        Returns:
            Device database object or None if not found.
        """
        return await self.s.get(Device, id)

    async def list_all(self) -> list[Device]:
        """Lists all registered devices ordered by created timestamp descending.

        Returns:
            List of registered devices.
        """
        r = await self.s.execute(select(Device).order_by(Device.created_at.desc()))
        return list(r.scalars().all())

    async def update_status(self, id: str, status: str) -> Device | None:
        """Updates device connectivity status and refreshes last_seen_at timestamp.

        Args:
            id: Target device ID.
            status: New connectivity tag.

        Returns:
            Updated Device database object, or None if not found.
        """
        d = await self.get(id)
        if not d:
            return None
        d.status = status
        d.last_seen_at = datetime.now(timezone.utc)
        await self.s.commit()
        await self.s.refresh(d)
        return d

    async def update(self, id: str, name: str, description: str | None) -> Device | None:
        """Updates name and description properties on a device record.

        Args:
            id: Target device ID.
            name: New display name.
            description: Optional new description.

        Returns:
            Updated Device database object, or None if not found.
        """
        d = await self.get(id)
        if not d:
            return None
        d.name = name
        if description is not None:
            d.description = description
        await self.s.commit()
        await self.s.refresh(d)
        return d

    async def delete(self, id: str) -> bool:
        """Removes a device record from the registry database.

        Args:
            id: Target device ID.

        Returns:
            True if deletion was successful, False otherwise.
        """
        d = await self.get(id)
        if not d:
            return False
        await self.s.delete(d)
        await self.s.commit()
        return True
