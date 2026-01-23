"""
Authentication service for user login and token management.

Handles user authentication, password verification, and user creation.
"""

from datetime import datetime, timezone
from typing import Optional

from backend.app.core.security import verify_password, hash_password, create_access_token
from backend.app.core.logging import get_logger
from backend.app.core.config import settings
from backend.app.models.user import User, UserRole

logger = get_logger(__name__)


class AuthService:
    """Service for authentication operations."""

    @staticmethod
    async def authenticate_user(email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password.

        Args:
            email: User email address
            password: Plaintext password

        Returns:
            User document if authentication successful, None otherwise
        """
        # Find user by email
        user = await User.find_one(User.email == email)

        if not user:
            logger.info("Authentication failed: user not found", email=email)
            return None

        # Verify password
        if not verify_password(password, user.hashed_password):
            logger.info("Authentication failed: invalid password", email=email)
            return None

        # Check if user is active
        if not user.is_active:
            logger.info("Authentication failed: user is inactive", email=email)
            return None

        # Update last login timestamp
        user.last_login = datetime.now(timezone.utc)
        await user.save()

        logger.info(
            "User authenticated successfully",
            email=email,
            role=user.role.value
        )

        return user

    @staticmethod
    def create_token_for_user(user: User) -> str:
        """
        Create JWT access token for authenticated user.

        Args:
            user: Authenticated User document

        Returns:
            JWT access token string
        """
        token_data = {
            "user_id": str(user.id),
            "sub": user.email,  # Subject claim (standard JWT field)
            "email": user.email,
            "role": user.role.value
        }

        return create_access_token(token_data)

    @staticmethod
    async def create_user(
        email: str,
        password: str,
        role: UserRole = UserRole.USER
    ) -> User:
        """
        Create a new user with hashed password.

        Args:
            email: User email address
            password: Plaintext password
            role: User role (default: USER)

        Returns:
            Created User document

        Raises:
            ValueError: If user with email already exists
        """
        # Check if user already exists
        existing_user = await User.find_one(User.email == email)
        if existing_user:
            logger.warning("User creation failed: email already exists", email=email)
            raise ValueError(f"User with email {email} already exists")

        # Create new user with hashed password
        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=True
        )

        await user.insert()

        logger.info(
            "User created successfully",
            email=email,
            role=role.value
        )

        return user

    @staticmethod
    async def get_user_by_email(email: str) -> Optional[User]:
        """
        Get user by email address.

        Args:
            email: User email address

        Returns:
            User document if found, None otherwise
        """
        return await User.find_one(User.email == email)

    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[User]:
        """
        Get user by MongoDB ObjectId.

        Args:
            user_id: User MongoDB ObjectId as string

        Returns:
            User document if found, None otherwise
        """
        try:
            return await User.get(user_id)
        except Exception as e:
            logger.warning("User not found by ID", user_id=user_id, error=str(e))
            return None
