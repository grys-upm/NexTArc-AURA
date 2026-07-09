"""Repository module wrapping database operations for Script records."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import Script

class ScriptRepository:
    """Provides SQL access query handlers wrapping Script database objects."""

    def __init__(self, s: AsyncSession):
        """Initializes the ScriptRepository.

        Args:
            s: SQLAlchemy async database session.
        """
        self.s = s

    async def create(
        self, name: str, description: str | None, language: str,
        script_key: str, script_sha256: str
    ) -> Script:
        """Registers a new inference script in the database.

        Args:
            name: Human-readable display name.
            description: Optional detailed notes.
            language: Target programming language ('python').
            script_key: MinIO file path storage locator key.
            script_sha256: SHA-256 hash checksum of script content.

        Returns:
            The created Script database entity.
        """
        sc = Script(name=name, description=description, language=language,
                    script_key=script_key, script_sha256=script_sha256)
        self.s.add(sc)
        await self.s.commit()
        await self.s.refresh(sc)
        return sc

    async def get(self, id: str) -> Script | None:
        """Retrieves a single script record by its UUID primary key.

        Args:
            id: Target script ID.

        Returns:
            Script object or None if not found.
        """
        return await self.s.get(Script, id)

    async def list_all(self) -> list[Script]:
        """Lists all registered scripts ordered by created timestamp descending.

        Returns:
            List of registered scripts.
        """
        r = await self.s.execute(select(Script).order_by(Script.created_at.desc()))
        return list(r.scalars().all())

    async def delete(self, id: str) -> bool:
        """Removes a script record from the registry database.

        Args:
            id: Target script ID.

        Returns:
            True if deletion was successful, False otherwise.
        """
        sc = await self.get(id)
        if not sc:
            return False
        await self.s.delete(sc)
        await self.s.commit()
        return True
