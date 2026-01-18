"""
User model with role-based access control.

Defines the User document for MongoDB with authentication fields.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from beanie import Document, Indexed
from pydantic import EmailStr, Field


class UserRole(str, Enum):
    """User role enumeration for RBAC."""
    ADMIN = "admin"  # Full access: create/modify/delete resources
    USER = "user"    # Read-only: view resources only


class User(Document):
    """
    Platform user with authentication credentials and role assignment.

    Indexes:
    - email (unique): Fast user lookup during authentication
    """

    email: Indexed(EmailStr, unique=True)
    hashed_password: str = Field(...)  # Excluded from API responses via schemas
    role: UserRole = Field(default=UserRole.USER)

    # Metadata
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    class Settings:
        name = "users"
        indexes = [
            "email",  # Unique index for authentication
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@example.com",
                "role": "admin",
                "is_active": True
            }
        }
