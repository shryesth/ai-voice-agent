"""
Database service helpers.

Provides convenient access to the MongoDB database instance for services and repositories.
"""

from typing import Optional
from pymongo.asynchronous.database import AsyncDatabase

from backend.app.core.database import db
from backend.app.core.config import settings


def get_database() -> Optional[AsyncDatabase]:
    """
    Get the MongoDB database instance.

    Returns:
        AsyncDatabase instance if connected, None otherwise
    """
    if db._client is None or not db._initialized:
        return None

    return db._client[settings.mongodb_database]


def get_database_safe() -> AsyncDatabase:
    """
    Get the MongoDB database instance (non-optional version).

    This function assumes the database has been initialized.
    Use this when you need a database instance and expect it to exist.

    Returns:
        AsyncDatabase instance

    Raises:
        RuntimeError: If database has not been initialized
    """
    if db._client is None or not db._initialized:
        raise RuntimeError(
            "Database not initialized. "
            "Ensure Database.connect() has been called during application startup."
        )

    return db._client[settings.mongodb_database]
