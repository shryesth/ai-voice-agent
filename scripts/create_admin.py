#!/usr/bin/env python3
"""
Admin user creation script.

Creates an initial admin user for the application.
Usage:
    python scripts/create_admin.py --email admin@example.com --password secure_password
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add backend to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.core.config import settings
from backend.app.core.database import db
from backend.app.core.security import hash_password
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


async def create_admin_user(email: str, password: str) -> None:
    """
    Create an admin user in the database.

    Args:
        email: Admin email address
        password: Admin password (will be hashed)
    """
    try:
        # Import User model (will be available after Phase 3)
        # For now, this is a placeholder
        from backend.app.models.user import User, UserRole

        logger.info("Creating admin user", email=email)

        # Check if user already exists
        existing_user = await User.find_one(User.email == email)
        if existing_user:
            logger.warning("User already exists", email=email)
            print(f"User with email '{email}' already exists")
            return

        # Create admin user
        admin_user = User(
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )

        await admin_user.insert()

        logger.info("Admin user created successfully", email=email)
        print(f"Admin user created: {email}")

    except ImportError:
        logger.error("User model not yet implemented")
        print("Error: User model not yet available. Run after Phase 3 implementation.")
        sys.exit(1)
    except Exception as e:
        logger.error("Failed to create admin user", error=str(e), exc_info=True)
        print(f"Error creating admin user: {e}")
        sys.exit(1)


async def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Create admin user")
    parser.add_argument(
        "--email",
        required=True,
        help="Admin email address"
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Admin password (min 8 characters)"
    )

    args = parser.parse_args()

    # Validate password length
    if len(args.password) < 8:
        print("Error: Password must be at least 8 characters")
        sys.exit(1)

    # Connect to database
    logger.info("Connecting to database")
    try:
        # Import models (will be available after Phase 3)
        from backend.app.models.user import User

        await db.connect(document_models=[User])
    except ImportError:
        # Models not yet available
        print("Note: User model not yet implemented. This script will work after Phase 3.")
        sys.exit(1)

    # Create admin user
    await create_admin_user(args.email, args.password)

    # Close database connection
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
