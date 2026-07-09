"""Repository module wrapping database operations for ModelRef mirror records."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import ModelRef

class CompilationRepository:
    """Provides SQL access query handlers wrapping ModelRef database objects."""

    def __init__(self, s: AsyncSession):
        """Initializes the CompilationRepository.

        Args:
            s: SQLAlchemy async database session.
        """
        self.s = s

    async def get_model_ref(self, model_id: str) -> ModelRef | None:
        """Retrieves a single ModelRef record by its primary key UUID.

        Args:
            model_id: Target model ID query request.

        Returns:
            ModelRef object or None if not found.
        """
        return await self.s.get(ModelRef, model_id)
