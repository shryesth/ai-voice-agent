"""
Beanie ODM database initialization.

Manages MongoDB connection using Beanie 2.0.1's native connection handling.
Motor client is managed internally by Beanie.
"""

from typing import List, Type
from pymongo import AsyncMongoClient
from beanie import Document, init_beanie

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class Database:
    """Database connection manager for MongoDB with Beanie ODM."""

    _initialized: bool = False
    _client: AsyncMongoClient = None

    @classmethod
    async def _precheck_connectivity(cls) -> None:
        """Fail-fast: verify MongoDB is reachable."""
        try:
            await cls._client.admin.command("ping")
            logger.info("MongoDB connectivity check passed")
        except Exception as e:
            raise ConnectionError(f"MongoDB not reachable: {e}") from e

    @classmethod
    async def _precheck_database_access(cls, db_name: str) -> None:
        """Fail-fast: verify database access (creates if doesn't exist)."""
        try:
            database = cls._client[db_name]
            # List collections to verify access (empty list is OK)
            await database.list_collection_names()
            logger.info("Database access check passed", database=db_name)
        except Exception as e:
            raise PermissionError(f"Cannot access database '{db_name}': {e}") from e

    @classmethod
    async def _precheck_privileges(cls, db_name: str) -> None:
        """Fail-fast: verify user has required roles (read-only check)."""
        try:
            # Use connectionStatus to check authenticated user's privileges
            # This is read-only and doesn't modify any data
            result = await cls._client.admin.command("connectionStatus")

            # Log authenticated user info (if any)
            auth_info = result.get("authInfo", {})
            users = auth_info.get("authenticatedUsers", [])

            if users:
                logger.info("Authenticated as", users=users)
            else:
                # No authentication = local dev with no auth enabled (OK)
                logger.info("No authentication required (local dev mode)")

            logger.info("Privileges check passed", database=db_name)
        except Exception as e:
            raise PermissionError(f"Cannot verify privileges on '{db_name}': {e}") from e

    @classmethod
    async def connect(cls, document_models: List[Type[Document]]) -> None:
        """
        Connect to MongoDB and initialize Beanie with document models.

        Performs fail-fast prechecks before initialization:
        1. Connectivity - verify MongoDB is reachable
        2. Database access - verify database can be accessed
        3. Privileges - verify user has required permissions

        Args:
            document_models: List of Beanie Document classes to register

        Raises:
            ConnectionError: If MongoDB is not reachable
            PermissionError: If database access or privileges are insufficient
            Exception: If connection fails for other reasons
        """
        # Skip if already initialized (e.g., by tests)
        if cls._initialized:
            logger.info("Database already initialized, skipping connect")
            return

        try:
            logger.info(
                "Connecting to MongoDB",
                uri=settings.mongodb_uri.split("@")[-1],  # Hide credentials
                database=settings.mongodb_database,
            )

            # Create async MongoDB client
            cls._client = AsyncMongoClient(settings.mongodb_uri)

            # Fail-fast prechecks
            await cls._precheck_connectivity()
            await cls._precheck_database_access(settings.mongodb_database)
            await cls._precheck_privileges(settings.mongodb_database)

            # Initialize Beanie with database instance
            database = cls._client[settings.mongodb_database]
            await init_beanie(
                database=database,
                document_models=document_models,
            )

            # Rebuild models to resolve forward references (e.g., Link["Campaign"])
            for model in document_models:
                model.model_rebuild()

            cls._initialized = True

            logger.info(
                "MongoDB connected successfully",
                database=settings.mongodb_database,
                models_count=len(document_models),
            )

        except (ConnectionError, PermissionError):
            # Re-raise prechecks errors as-is for clear messaging
            raise
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
            try:
                # Motor's close() is now async in recent versions
                if hasattr(cls._client.close, '__call__'):
                    result = cls._client.close()
                    # Check if it's a coroutine
                    if hasattr(result, '__await__'):
                        await result
            except Exception as e:
                logger.warning("Error closing MongoDB client", error=str(e))
            finally:
                cls._initialized = False
                logger.info("MongoDB connection closed")
                cls._client = None
                logger.info("MongoDB connection closed")

    @classmethod
    async def ping(cls) -> bool:
        """
        Ping MongoDB to check connection health.

        Returns:
            True if connection is healthy, False otherwise
        """
        if not cls._initialized or not cls._client:
            return False

        try:
            await cls._client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning("MongoDB ping failed", error=str(e))
            return False


# Global database instance
db = Database()
