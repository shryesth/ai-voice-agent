"""
Authentication API endpoints.

Endpoints:
- POST /api/v1/auth/login - User authentication
- GET /api/v1/auth/me - Get current user info
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.app.core.security import decode_access_token
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.models.user import User, UserRole
from backend.app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    CurrentUserResponse
)
from backend.app.services.auth_service import AuthService

logger = get_logger(__name__)
router = APIRouter()
security = HTTPBearer()


# Dependency: Get current user from JWT token
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> User:
    """
    Get current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        Authenticated User document

    Raises:
        HTTPException 401: If token is invalid or user not found
    """
    token = credentials.credentials

    # Decode JWT token
    payload = decode_access_token(token)
    if not payload:
        logger.warning("Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user ID from token
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Token missing user_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    user = await AuthService.get_user_by_id(user_id)
    if not user:
        logger.warning("User not found for token", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        logger.warning("Inactive user attempted access", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    return user


# Dependency: Require admin role
async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Require current user to have admin role.

    Args:
        current_user: Current authenticated user

    Returns:
        User if admin role

    Raises:
        HTTPException 403: If user is not admin
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin user attempted admin action",
            email=current_user.email,
            role=current_user.role.value
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return access token.

    Args:
        request: Login credentials (email, password)

    Returns:
        LoginResponse with access_token and user info

    Raises:
        HTTPException 401: If credentials are invalid
    """
    # Authenticate user
    user = await AuthService.authenticate_user(request.email, request.password)

    if not user:
        # Use generic error message to prevent user enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Create JWT token
    access_token = AuthService.create_token_for_user(user)

    # Calculate expiration in seconds
    expires_in = settings.jwt_expiration_hours * 3600

    logger.info(
        "User logged in successfully",
        email=user.email,
        role=user.role.value
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserResponse(
            email=user.email,
            role=user.role,
            is_active=user.is_active
        )
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get current authenticated user information.

    Args:
        current_user: Current authenticated user from JWT token

    Returns:
        CurrentUserResponse with user details and timestamps
    """
    logger.debug("User accessed /me endpoint", email=current_user.email)

    return CurrentUserResponse(
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login=current_user.last_login
    )
