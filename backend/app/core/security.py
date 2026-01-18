"""
Security utilities for authentication and authorization.

Provides JWT token management and password hashing with bcrypt.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

# Password hashing context with bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Args:
        password: Plaintext password

    Returns:
        Hashed password string

    Example:
        >>> hashed = hash_password("secure_password_123")
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a hashed password.

    Args:
        plain_password: Plaintext password to verify
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise

    Example:
        >>> is_valid = verify_password("user_input", stored_hash)
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode (typically user_id, email, role)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token(
        ...     data={"user_id": "123", "email": "admin@example.com", "role": "admin"}
        ... )
    """
    to_encode = data.copy()

    # Set expiration time
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiration_hours)

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

    # Encode JWT
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    logger.debug(
        "Access token created",
        user_id=data.get("user_id"),
        email=data.get("email"),
        expires_at=expire.isoformat(),
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT access token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload if valid, None if invalid/expired

    Example:
        >>> payload = decode_access_token(token)
        >>> if payload:
        ...     user_id = payload.get("user_id")
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        # Verify required fields
        if "user_id" not in payload:
            logger.warning("Token missing user_id field")
            return None

        return payload

    except JWTError as e:
        logger.warning("JWT decode failed", error=str(e))
        return None


def verify_token(token: str) -> bool:
    """
    Verify if a token is valid without decoding full payload.

    Args:
        token: JWT token string

    Returns:
        True if token is valid and not expired

    Example:
        >>> if verify_token(token):
        ...     # Token is valid
        ...     pass
    """
    payload = decode_access_token(token)
    return payload is not None


def get_token_expiration(token: str) -> Optional[datetime]:
    """
    Get expiration datetime from a token.

    Args:
        token: JWT token string

    Returns:
        Expiration datetime if token is valid, None otherwise
    """
    payload = decode_access_token(token)
    if not payload:
        return None

    exp_timestamp = payload.get("exp")
    if not exp_timestamp:
        return None

    return datetime.fromtimestamp(exp_timestamp)
