"""
Pytest configuration and shared fixtures for all tests.

Provides:
- async_client: HTTPX async client for API testing
- test_admin_user: Pre-seeded admin user credentials
- auth_headers: Authorization headers with valid JWT token
- test_db: Database connection for test isolation
"""

import os

# Skip startup validation so tests control the database connection
os.environ["SKIP_STARTUP_VALIDATION"] = "true"

# Disable bootstrap admin creation during tests (tests manage users explicitly)
os.environ["ENABLE_BOOTSTRAP_ADMIN"] = "false"

import pytest
import pytest_asyncio
from typing import AsyncGenerator, Dict
from httpx import AsyncClient, ASGITransport
from beanie import init_beanie

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.security import create_access_token, hash_password
from backend.app.models.user import User, UserRole


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator:
    """
    Provide test database connection with isolation.

    Uses Beanie's native connection handling. Creates a test database,
    yields connection, then cleans up.
    """
    from pymongo import AsyncMongoClient
    from backend.app.core.database import Database

    # Use a separate test database
    test_db_name = f"{settings.mongodb_database}_test"

    # Create MongoDB client and database
    client = AsyncMongoClient(settings.mongodb_uri)
    db = client[test_db_name]

    # Import models for registration
    from backend.app.models.user import User
    from backend.app.models.geography import Geography
    from backend.app.models.campaign import Campaign
    from backend.app.models.call_record import CallRecord
    from backend.app.models.queue_entry import QueueEntry

    # Initialize Beanie with test database
    await init_beanie(
        database=db,
        document_models=[User, Geography, Campaign, CallRecord, QueueEntry]
    )

    # Mark database as initialized so app's lifespan skips db.connect()
    Database._initialized = True
    Database._client = client

    yield db

    # Cleanup: Drop test database after tests
    Database._initialized = False
    Database._client = None
    await client.drop_database(test_db_name)
    client.close()


@pytest_asyncio.fixture
async def async_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide async HTTP client for testing FastAPI endpoints.

    Uses HTTPX AsyncClient with ASGI transport for direct app testing
    without running a server.

    Depends on test_db to ensure Beanie is initialized before any requests.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def test_admin_user() -> Dict[str, str]:
    """
    Provide test admin user credentials.

    Returns:
        Dict with email and password for testing authentication
    """
    return {
        "email": "admin@example.com",
        "password": "TestPassword123!",
        "role": "admin"
    }


@pytest.fixture
def test_regular_user() -> Dict[str, str]:
    """
    Provide test regular user credentials.

    Returns:
        Dict with email and password for testing non-admin access
    """
    return {
        "email": "user@example.com",
        "password": "UserPassword123!",
        "role": "user"
    }


@pytest_asyncio.fixture
async def seeded_admin_user(test_db, test_admin_user) -> User:
    """
    Create and return a seeded admin user in the database.

    Returns:
        Created User document
    """
    from backend.app.models.user import User, UserRole

    # Check if user already exists
    existing_user = await User.find_one(User.email == test_admin_user["email"])
    if existing_user:
        await existing_user.delete()

    # Create new user
    user = User(
        email=test_admin_user["email"],
        hashed_password=hash_password(test_admin_user["password"]),
        role=UserRole.ADMIN,
        is_active=True
    )
    await user.insert()

    return user


@pytest_asyncio.fixture
async def auth_token(test_admin_user, seeded_admin_user) -> str:
    """
    Generate a valid JWT token for testing authenticated endpoints.

    Depends on seeded_admin_user to ensure user exists and include user_id.

    Returns:
        JWT access token string
    """
    token_data = {
        "user_id": str(seeded_admin_user.id),
        "sub": test_admin_user["email"],
        "email": test_admin_user["email"],
        "role": test_admin_user["role"]
    }
    return create_access_token(token_data)


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> Dict[str, str]:
    """
    Provide authorization headers with valid JWT token.

    Returns:
        Dict with Authorization header
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def seeded_regular_user(test_db, test_regular_user) -> User:
    """
    Create and return a seeded regular user in the database.

    Returns:
        Created User document
    """
    from backend.app.models.user import User, UserRole

    # Check if user already exists
    existing_user = await User.find_one(User.email == test_regular_user["email"])
    if existing_user:
        await existing_user.delete()

    # Create new user
    user = User(
        email=test_regular_user["email"],
        hashed_password=hash_password(test_regular_user["password"]),
        role=UserRole.USER,
        is_active=True
    )
    await user.insert()

    return user


@pytest_asyncio.fixture
async def user_token(test_regular_user, seeded_regular_user) -> str:
    """
    Generate a valid JWT token for regular (non-admin) user.

    Depends on seeded_regular_user to ensure user exists and include user_id.

    Returns:
        JWT access token string
    """
    token_data = {
        "user_id": str(seeded_regular_user.id),
        "sub": test_regular_user["email"],
        "email": test_regular_user["email"],
        "role": test_regular_user["role"]
    }
    return create_access_token(token_data)


@pytest_asyncio.fixture
async def user_auth_headers(user_token: str) -> Dict[str, str]:
    """
    Provide authorization headers for regular (non-admin) user.

    Returns:
        Dict with Authorization header for non-admin user
    """
    return {"Authorization": f"Bearer {user_token}"}


# Test data factories

@pytest.fixture
def valid_phone_number() -> str:
    """Provide a valid E.164 formatted phone number."""
    return "+12025551234"


@pytest.fixture
def invalid_phone_numbers() -> list[str]:
    """Provide list of invalid phone number formats."""
    return [
        "12025551234",  # Missing +
        "+1202555",     # Too short
        "202-555-1234", # Wrong format
        "+abc",         # Non-numeric
        "",             # Empty
    ]


@pytest.fixture
def test_campaign_data() -> Dict:
    """Provide valid campaign creation data."""
    return {
        "name": "Test Campaign - January 2026",
        "config": {
            "max_concurrent_calls": 5,
            "patient_list": ["+12025551234", "+12025555678"],
            "language_preference": "en",
            "time_windows": []
        }
    }


@pytest.fixture
def test_geography_data() -> Dict:
    """Provide valid geography creation data."""
    return {
        "name": "Test Region - North America",
        "region_code": "US-TEST",
        "retention_policy": {
            "retention_days": 365,
            "compliance_notes": "Test data retention policy"
        }
    }
