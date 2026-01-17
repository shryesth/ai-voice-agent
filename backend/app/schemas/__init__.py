"""
Base Pydantic schemas for request/response models.

Provides common response schemas used across all endpoints.
"""

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Standard message response for operations without specific return data."""

    message: str = Field(..., description="Success or status message")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Operation completed successfully"
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response for API errors."""

    detail: str | list = Field(..., description="Error message or validation errors")

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Resource not found"
            }
        }


__all__ = ["MessageResponse", "ErrorResponse"]
