"""
Campaign API endpoints.

Endpoints:
- POST /api/v1/geographies/{geography_id}/campaigns - Create campaign under geography (Admin only)
- GET /api/v1/campaigns - List campaigns with filtering
- GET /api/v1/campaigns/{campaign_id} - Get campaign by ID
- PATCH /api/v1/campaigns/{campaign_id} - Update campaign (Admin only)
- POST /api/v1/campaigns/{campaign_id}/start - Start campaign (Admin only)
- POST /api/v1/campaigns/{campaign_id}/pause - Pause campaign (Admin only)
- POST /api/v1/campaigns/{campaign_id}/resume - Resume campaign (Admin only)
- POST /api/v1/campaigns/{campaign_id}/cancel - Cancel campaign (Admin only)
- GET /api/v1/campaigns/{campaign_id}/status - Get campaign status
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status

from backend.app.models.user import User, UserRole
from backend.app.models.campaign import CampaignState
from backend.app.schemas.campaign import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
    CampaignStateChangeResponse,
    CampaignStatusResponse,
    CampaignConfigResponse,
)
from backend.app.services.campaign_service import CampaignService
from backend.app.api.v1.auth import get_current_user, require_admin
from backend.app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def campaign_to_response(campaign, user: User) -> CampaignResponse:
    """
    Convert Campaign document to response schema.

    Hides patient_list from User role for privacy protection.

    Args:
        campaign: Campaign document from database
        user: Current authenticated user

    Returns:
        CampaignResponse schema
    """
    # Convert config, hiding patient_list for User role
    config = campaign.config
    config_dict = config.model_dump() if hasattr(config, 'model_dump') else dict(config)

    # Hide patient list from User role
    if user.role == UserRole.USER:
        config_dict["patient_list"] = []

    return CampaignResponse(
        id=str(campaign.id),
        geography_id=str(campaign.geography_id.ref.id),
        name=campaign.name,
        state=campaign.state,
        config=CampaignConfigResponse(**config_dict),
        stats=campaign.stats,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
    )


@router.post(
    "/geographies/{geography_id}/campaigns",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_campaign(
    geography_id: str = Path(..., description="Geography MongoDB ObjectId"),
    data: CampaignCreate = ...,
    current_user: Annotated[User, Depends(require_admin)] = ...
):
    """
    Create new campaign within geography (Admin role only).

    Args:
        geography_id: Parent geography MongoDB ObjectId
        data: Campaign creation data
        current_user: Current authenticated admin user

    Returns:
        Created campaign with ID and timestamps

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If geography not found
        HTTPException 422: If phone numbers are invalid
    """
    try:
        campaign = await CampaignService.create_campaign(geography_id, data)
        logger.info(
            "Campaign created via API",
            campaign_id=str(campaign.id),
            geography_id=geography_id,
            admin_email=current_user.email
        )
        return campaign_to_response(campaign, current_user)
    except ValueError as e:
        # Geography not found error
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    current_user: Annotated[User, Depends(get_current_user)],
    geography_id: Optional[str] = Query(None, description="Filter by geography"),
    state: Optional[CampaignState] = Query(None, description="Filter by state"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size (max 100)")
):
    """
    List all campaigns with optional filtering (both Admin and User roles).

    Patient lists are hidden from User role responses.

    Args:
        current_user: Current authenticated user
        geography_id: Optional filter by geography
        state: Optional filter by state
        skip: Pagination offset
        limit: Page size

    Returns:
        Paginated list of campaigns with total count
    """
    campaigns, total = await CampaignService.list_campaigns(
        geography_id=geography_id,
        state=state,
        skip=skip,
        limit=limit
    )

    logger.debug(
        "Campaigns listed via API",
        total=total,
        user_email=current_user.email
    )

    return CampaignListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[campaign_to_response(c, current_user) for c in campaigns]
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get campaign by ID with full details (both Admin and User roles).

    Patient list is hidden from User role response.

    Args:
        campaign_id: MongoDB ObjectId as string
        current_user: Current authenticated user

    Returns:
        Campaign with full details

    Raises:
        HTTPException 404: If campaign not found
    """
    campaign = await CampaignService.get_campaign_by_id(campaign_id)

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )

    logger.debug("Campaign retrieved via API", campaign_id=campaign_id)

    return campaign_to_response(campaign, current_user)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: str,
    data: CampaignUpdate,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Update campaign configuration (Admin role only).

    Only allowed in DRAFT or PAUSED state.

    Args:
        campaign_id: MongoDB ObjectId as string
        data: Partial update data
        current_user: Current authenticated admin user

    Returns:
        Updated campaign

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If campaign not found
        HTTPException 409: If campaign is ACTIVE (cannot modify running campaign)
    """
    try:
        campaign = await CampaignService.update_campaign(campaign_id, data)

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )

        logger.info(
            "Campaign updated via API",
            campaign_id=campaign_id,
            admin_email=current_user.email
        )

        return campaign_to_response(campaign, current_user)
    except ValueError as e:
        # Active campaign error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/{campaign_id}/start", response_model=CampaignStateChangeResponse)
async def start_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Start campaign (transition from DRAFT → ACTIVE).

    Creates queue entries for all patients in patient_list.

    Args:
        campaign_id: MongoDB ObjectId as string
        current_user: Current authenticated admin user

    Returns:
        Campaign state change confirmation

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If campaign not found
        HTTPException 409: If campaign already started
    """
    try:
        campaign = await CampaignService.start_campaign(campaign_id)

        logger.info(
            "Campaign started via API",
            campaign_id=campaign_id,
            admin_email=current_user.email,
            total_calls=campaign.stats.total_calls
        )

        return CampaignStateChangeResponse(
            id=str(campaign.id),
            state=campaign.state,
            started_at=campaign.started_at,
            completed_at=campaign.completed_at,
            message=f"Campaign started. Queue entries created for {campaign.stats.total_calls} patients."
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/{campaign_id}/pause", response_model=CampaignStateChangeResponse)
async def pause_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Pause campaign (transition from ACTIVE → PAUSED).

    In-progress calls continue, but no new calls are initiated.

    Args:
        campaign_id: MongoDB ObjectId as string
        current_user: Current authenticated admin user

    Returns:
        Campaign state change confirmation

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If campaign not found
        HTTPException 409: If campaign not active
    """
    try:
        campaign = await CampaignService.pause_campaign(campaign_id)

        logger.info(
            "Campaign paused via API",
            campaign_id=campaign_id,
            admin_email=current_user.email
        )

        in_progress = campaign.stats.in_progress_count
        queued = campaign.stats.queued_count

        message = (
            f"Campaign paused. {in_progress} calls in progress will complete. "
            f"{queued} queued calls will not be processed until resumed."
        )

        return CampaignStateChangeResponse(
            id=str(campaign.id),
            state=campaign.state,
            started_at=campaign.started_at,
            completed_at=campaign.completed_at,
            message=message
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/{campaign_id}/resume", response_model=CampaignStateChangeResponse)
async def resume_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Resume paused campaign (transition from PAUSED → ACTIVE).

    Args:
        campaign_id: MongoDB ObjectId as string
        current_user: Current authenticated admin user

    Returns:
        Campaign state change confirmation

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If campaign not found
        HTTPException 409: If campaign not paused
    """
    try:
        campaign = await CampaignService.resume_campaign(campaign_id)

        logger.info(
            "Campaign resumed via API",
            campaign_id=campaign_id,
            admin_email=current_user.email
        )

        queued = campaign.stats.queued_count
        message = f"Campaign resumed. Processing {queued} queued calls."

        return CampaignStateChangeResponse(
            id=str(campaign.id),
            state=campaign.state,
            started_at=campaign.started_at,
            completed_at=campaign.completed_at,
            message=message
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/{campaign_id}/cancel", response_model=CampaignStateChangeResponse)
async def cancel_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(require_admin)]
):
    """
    Cancel campaign permanently (transition to CANCELLED state).

    In-progress calls continue, but all pending calls are removed from queue.
    This is a terminal state - campaign cannot be resumed.

    Args:
        campaign_id: MongoDB ObjectId as string
        current_user: Current authenticated admin user

    Returns:
        Campaign state change confirmation

    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If campaign not found
        HTTPException 409: If campaign already in terminal state
    """
    try:
        campaign = await CampaignService.cancel_campaign(campaign_id)

        logger.info(
            "Campaign cancelled via API",
            campaign_id=campaign_id,
            admin_email=current_user.email
        )

        message = "Campaign cancelled. All pending calls removed from queue."

        return CampaignStateChangeResponse(
            id=str(campaign.id),
            state=campaign.state,
            started_at=campaign.started_at,
            completed_at=campaign.completed_at,
            message=message
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.get("/{campaign_id}/status", response_model=CampaignStatusResponse)
async def get_campaign_status(
    campaign_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get real-time campaign execution status (both Admin and User roles).

    Returns progress metrics, concurrency, and estimated completion.

    Args:
        campaign_id: MongoDB ObjectId as string
        current_user: Current authenticated user

    Returns:
        Real-time campaign status with progress tracking

    Raises:
        HTTPException 404: If campaign not found
    """
    status_data = await CampaignService.get_campaign_status(campaign_id)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )

    logger.debug(
        "Campaign status retrieved via API",
        campaign_id=campaign_id,
        user_email=current_user.email
    )

    return CampaignStatusResponse(**status_data)
