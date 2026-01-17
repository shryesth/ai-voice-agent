"""
Beanie ODM database initialization.

Manages MongoDB connection using Beanie 2.0.1's native connection handling.
Motor client is managed internally by Beanie.
"""

from typing import List, Type
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import Document, init_beanie

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class Database:
    """Database connection manager for MongoDB with Beanie ODM."""

    _initialized: bool = False
    _client: AsyncIOMotorClient = None

    @classmethod
    async def connect(cls, document_models: List[Type[Document]]) -> None:
        """
        Connect to MongoDB and initialize Beanie with document models.

        Uses Beanie 2.0.1's native connection_string parameter which
        handles motor client creation internally.

        Args:
            document_models: List of Beanie Document classes to register

        Raises:
            Exception: If connection fails
        """
        try:
            logger.info(
                "Connecting to MongoDB",
                uri=settings.mongodb_uri.split("@")[-1],  # Hide credentials
                database=settings.mongodb_database,
            )

            # Create motor client and get database
            cls._client = AsyncIOMotorClient(settings.mongodb_uri)
            database = cls._client[settings.mongodb_database]

            # Initialize Beanie with database instance
            await init_beanie(
                database=database,
                document_models=document_models,
            )

            cls._initialized = True

            logger.info(
                "MongoDB connected successfully",
                database=settings.mongodb_database,
                models_count=len(document_models),
            )

        except Exception as e:
            logger.error(
                "Failed to connect to MongoDB",
                error=str(e),
                uri=settings.mongodb_uri.split("@")[-1],
            )
            raise

    @classmethod
    async def close(cls) -> None:
        """Close MongoDB connection gracefully."""
        if cls._initialized and cls._client:
            cls._client.close()
            cls._initialized = False
            logger.info("MongoDB connection closed")

    @classmethod
    async def ping(cls) -> bool:
        """
        Ping MongoDB to check connection health.

        Uses Beanie's internal motor client to execute ping command.

        Returns:
            True if connection is healthy, False otherwise
        """
        if not cls._initialized:
            return False

        try:
            # Access the motor database through any registered Document class
            # Beanie stores the database reference internally
            from beanie.odm.utils.state import current_state

            motor_db = current_state.database
            if motor_db is None:
                return False

            await motor_db.client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning("MongoDB ping failed", error=str(e))
            return False


# Global database instance
db = Database()
