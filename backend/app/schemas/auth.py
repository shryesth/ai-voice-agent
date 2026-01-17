"""
Authentication request/response schemas.

Pydantic models for:
- Login request
- Login response
- User response
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

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
