"""
Authentication API endpoints.

Endpoints:
- POST /api/v1/auth/login - User authentication
- GET /api/v1/auth/me - Get current user info
- POST /api/v1/auth/admin - Create new admin user (Admin only)
- DELETE /api/v1/auth/admin/{user_id} - Delete admin user (Admin only)
"""

from datetime import datetime, timezone
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
    CurrentUserResponse,
    CreateAdminRequest,
    AdminCreatedResponse
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


@router.post(
    "/admin",
    response_model=AdminCreatedResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_admin(
    request: CreateAdminRequest,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Create a new admin user (Admin only).

    Only existing admin users can create new admin accounts.
    Password must meet security requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        request: Admin creation request (email, password)
        current_user: Current authenticated admin user

    Returns:
        AdminCreatedResponse with created admin details

    Raises:
        HTTPException 403: If current user is not admin
        HTTPException 409: If email already exists
        HTTPException 422: If password validation fails
    """
    try:
        # Create admin user using AuthService
        new_admin = await AuthService.create_user(
            email=request.email,
            password=request.password,
            role=UserRole.ADMIN
        )

        logger.info(
            "Admin user created",
            new_admin_email=new_admin.email,
            created_by_admin=current_user.email,
            new_admin_id=str(new_admin.id)
        )

        return AdminCreatedResponse(
            id=str(new_admin.id),
            email=new_admin.email,
            role=new_admin.role,
            is_active=new_admin.is_active,
            created_at=new_admin.created_at,
            message="Admin user created successfully"
        )

    except ValueError as e:
        # Email already exists
        logger.warning(
            "Admin creation failed: duplicate email",
            email=request.email,
            attempted_by=current_user.email
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.delete("/admin/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(
    user_id: str,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Delete an admin user (Admin only).

    Soft deletes an admin user by setting is_active=False.
    This endpoint includes several safety checks:
    - Prevents self-deletion (cannot delete your own account)
    - Prevents deleting the last admin (ensures ≥1 admin always exists)
    - Only allows deletion of admin users (not regular users)

    Args:
        user_id: MongoDB ObjectId of the admin user to delete
        current_user: Current authenticated admin user

    Returns:
        204 NO_CONTENT on success

    Raises:
        HTTPException 400: If target user is not an admin
        HTTPException 403: If current user is not admin
        HTTPException 404: If target user not found
        HTTPException 409: If attempting self-deletion or deleting last admin
    """
    # Validation 1: Prevent self-deletion
    if str(current_user.id) == user_id:
        logger.warning(
            "Admin attempted self-deletion",
            admin_email=current_user.email,
            user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete your own admin account. Please use another admin account to perform this action."
        )

    # Validation 2: Verify target user exists
    target_user = await AuthService.get_user_by_id(user_id)
    if not target_user:
        logger.warning(
            "Admin deletion failed: user not found",
            user_id=user_id,
            attempted_by=current_user.email
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    # Validation 3: Verify target is an admin
    if target_user.role != UserRole.ADMIN:
        logger.warning(
            "Admin deletion failed: target is not an admin",
            target_email=target_user.email,
            target_role=target_user.role.value,
            attempted_by=current_user.email
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {target_user.email} is not an admin. Use appropriate endpoint to manage non-admin users."
        )

    # Validation 4: Prevent deleting the last admin
    active_admin_count = await User.find(
        User.role == UserRole.ADMIN,
        User.is_active == True
    ).count()

    if active_admin_count <= 1:
        logger.warning(
            "Admin deletion failed: cannot delete last admin",
            target_email=target_user.email,
            attempted_by=current_user.email,
            active_admin_count=active_admin_count
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete the last admin user. Create another admin before deleting this account."
        )

    # Perform soft delete
    target_user.is_active = False
    target_user.updated_at = datetime.now(timezone.utc)
    await target_user.save()

    logger.info(
        "Admin user deleted (soft delete)",
        deleted_admin_email=target_user.email,
        deleted_by_admin=current_user.email,
        deleted_admin_id=user_id
    )

    return None  # FastAPI automatically returns 204 NO_CONTENT
