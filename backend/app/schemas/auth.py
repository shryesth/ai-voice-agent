"""
Authentication request/response schemas.

Pydantic models for:
- Login request
- Login response
- User response
"""

from datetime import datetime
from typing import Optional
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.app.models.user import UserRole


class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    """Basic user information response."""
    email: EmailStr
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True  # Enable ORM mode for Beanie documents


class CurrentUserResponse(UserResponse):
    """Extended user response with timestamps for /auth/me endpoint."""
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login success response with JWT token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Token expiration in seconds
    user: UserResponse


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


class CreateAdminRequest(BaseModel):
    """Request schema for creating a new admin user."""
    email: EmailStr = Field(..., description="Email address for the new admin user")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password for the new admin user (min 8 chars, must include uppercase, lowercase, digit, special char)"
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password meets security requirements.

        Requirements:
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character

        Raises:
            ValueError: If password doesn't meet requirements
        """
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>?/]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class AdminCreatedResponse(BaseModel):
    """Response schema for successful admin creation."""
    id: str = Field(..., description="User ID of the newly created admin")
    email: EmailStr = Field(..., description="Email address of the admin")
    role: UserRole = Field(..., description="User role (always 'admin')")
    is_active: bool = Field(..., description="Whether the admin account is active")
    created_at: datetime = Field(..., description="Timestamp when the admin was created")
    message: str = Field(
        default="Admin user created successfully",
        description="Success message"
    )

    class Config:
        from_attributes = True
