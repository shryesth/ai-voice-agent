"""
Beanie ODM database initialization.

Manages MongoDB connection and Beanie document initialization.
"""

from typing import List, Type
from beanie import Document, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class Database:
    """Database connection manager for MongoDB with Beanie ODM."""

    client: AsyncIOMotorClient | None = None

    @classmethod
    async def connect(cls, document_models: List[Type[Document]]) -> None:
        """
        Connect to MongoDB and initialize Beanie with document models.

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

            # Create async motor client
            cls.client = AsyncIOMotorClient(settings.mongodb_uri)

            # Initialize Beanie with document models
            await init_beanie(
                database=cls.client[settings.mongodb_database],
                document_models=document_models,
            )

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
        if cls.client:
            logger.info("Closing MongoDB connection")
            cls.client.close()
            cls.client = None
            logger.info("MongoDB connection closed")

    @classmethod
    async def ping(cls) -> bool:
        """
        Ping MongoDB to check connection health.

        Returns:
            True if connection is healthy, False otherwise
        """
        if not cls.client:
            return False

        try:
            await cls.client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning("MongoDB ping failed", error=str(e))
            return False


# Global database instance
db = Database()
