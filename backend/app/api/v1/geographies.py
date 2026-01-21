"""
Geography API endpoints.

Endpoints:
- POST /api/v1/geographies - Create geography (Admin only)
- GET /api/v1/geographies - List geographies with filtering
- GET /api/v1/geographies/{geography_id} - Get geography by ID
- PATCH /api/v1/geographies/{geography_id} - Update geography (Admin only)
- DELETE /api/v1/geographies/{geography_id} - Soft delete geography (Admin only)
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.models.user import User
from backend.app.schemas.geography import (
    GeographyCreate,
    GeographyUpdate,
    GeographyResponse,
    GeographyListResponse,
)
from backend.app.services.geography_service import GeographyService
from backend.app.api.v1.auth import get_current_user, require_admin
from backend.app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def geography_to_response(geography) -> GeographyResponse:
    """
    Convert Geography document to response schema.

    Args:
        geography: Geography document from database

    Returns:
        GeographyResponse schema
    """
    return GeographyResponse(
        id=str(geography.id),
        name=geography.name,
        description=geography.description,
        region_code=geography.region_code,
        clarity_config=geography.clarity_config,
        retention_policy=geography.retention_policy,
        metadata=geography.metadata,
        created_at=geography.created_at,
        updated_at=geography.updated_at,
    )


@router.post("", response_model=GeographyResponse, status_code=status.HTTP_201_CREATED)
async def create_geography(
    data: GeographyCreate,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Create new geography (Admin role only).

    Args:
        data: Geography creation data
        current_user: Current authenticated admin user

    Returns:
        Created geography with ID and timestamps

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 409: If geography with same name already exists
    """
    try:
        geography = await GeographyService.create_geography(data)
        logger.info(
            "Geography created via API",
            geography_id=str(geography.id),
            admin_email=current_user.email
        )
        return geography_to_response(geography)
    except ValueError as e:
        # Duplicate name error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.get("", response_model=GeographyListResponse)
async def list_geographies(
    current_user: Annotated[User, Depends(get_current_user)],
    region_code: Optional[str] = Query(None, description="Filter by region code"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size (max 100)")
):
    """
    List all geographies with optional filtering (both Admin and User roles).

    Args:
        current_user: Current authenticated user
        region_code: Optional filter by region code
        skip: Pagination offset
        limit: Page size

    Returns:
        Paginated list of geographies with total count
    """
    geographies, total = await GeographyService.list_geographies(
        region_code=region_code,
        skip=skip,
        limit=limit
    )

    logger.debug(
        "Geographies listed via API",
        total=total,
        user_email=current_user.email
    )

    return GeographyListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[geography_to_response(g) for g in geographies]
    )


@router.get("/{geography_id}", response_model=GeographyResponse)
async def get_geography(
    geography_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get geography by ID with full details (both Admin and User roles).

    Args:
        geography_id: MongoDB ObjectId as string
        current_user: Current authenticated user

    Returns:
        Geography with full details

    Raises:
        HTTPException 404: If geography not found
    """
    geography = await GeographyService.get_geography_by_id(geography_id)

    if not geography:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geography not found"
        )

    logger.debug("Geography retrieved via API", geography_id=geography_id)

    return geography_to_response(geography)


@router.patch("/{geography_id}", response_model=GeographyResponse)
async def update_geography(
    geography_id: str,
    data: GeographyUpdate,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Update geography (partial update, Admin role only).

    Args:
        geography_id: MongoDB ObjectId as string
        data: Partial update data
        current_user: Current authenticated admin user

    Returns:
        Updated geography

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If geography not found
        HTTPException 409: If updating name to an existing name
    """
    try:
        geography = await GeographyService.update_geography(geography_id, data)

        if not geography:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Geography not found"
            )

        logger.info(
            "Geography updated via API",
            geography_id=geography_id,
            admin_email=current_user.email
        )

        return geography_to_response(geography)
    except ValueError as e:
        # Duplicate name error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.delete("/{geography_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geography(
    geography_id: str,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Soft delete geography (Admin role only).

    Sets deleted_at timestamp. Prevents deletion if geography has active campaigns.

    Args:
        geography_id: MongoDB ObjectId as string
        current_user: Current authenticated admin user

    Returns:
        204 No Content on success

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If geography not found
        HTTPException 409: If geography has active campaigns
    """
    try:
        deleted = await GeographyService.delete_geography(geography_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Geography not found"
            )

        logger.info(
            "Geography soft deleted via API",
            geography_id=geography_id,
            admin_email=current_user.email
        )

        return None
    except ValueError as e:
        # Active campaigns error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
