"""
API routes for campaign queue management and DLQ operations.

Endpoints:
- GET /api/v1/campaigns/{id}/queue - Get campaign queue status
- GET /api/v1/queue/dlq - List DLQ entries (Admin)
- POST /api/v1/queue/dlq/{id}/retry - Manually retry DLQ entry (Admin)
- DELETE /api/v1/queue/dlq/{id} - Remove DLQ entry (Admin)
- GET /api/v1/queue/stats - Global queue statistics (Admin)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
import logging

from backend.app.models.user import User, UserRole
from backend.app.models.queue_entry import QueueState
from backend.app.schemas.queue import (
    QueueEntryResponse,
    QueueListResponse,
    QueueSummaryResponse,
    DLQResponse,
    DLQListResponse,
    DLQRetryRequest,
    GlobalQueueStatsResponse,
    RetryHistoryResponse
)
from backend.app.services.queue_service import QueueService
from backend.app.api.v1.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def queue_entry_to_response(entry) -> QueueEntryResponse:
    """Convert QueueEntry to QueueEntryResponse schema"""
    return QueueEntryResponse(
        id=str(entry.id),
        campaign_id=entry.campaign_id,
        call_record_id=entry.call_record_id,
        patient_phone=entry.patient_phone,
        language=entry.language,
        state=entry.state,
        retry_count=entry.retry_count,
        retry_history=[
            RetryHistoryResponse(
                attempt_number=r.attempt_number,
                attempted_at=r.attempted_at,
                failure_reason=r.failure_reason,
                error_details=r.error_details
            )
            for r in entry.retry_history
        ],
        next_retry_at=entry.next_retry_at,
        last_failure_reason=entry.last_failure_reason,
        moved_to_dlq=entry.moved_to_dlq,
        dlq_reason=entry.dlq_reason,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        first_attempted_at=entry.first_attempted_at,
        completed_at=entry.completed_at
    )


def queue_entry_to_dlq_response(entry) -> DLQResponse:
    """Convert QueueEntry to DLQResponse schema"""
    return DLQResponse(
        id=str(entry.id),
        campaign_id=entry.campaign_id,
        call_record_id=entry.call_record_id,
        patient_phone=entry.patient_phone,
        language=entry.language,
        retry_count=entry.retry_count,
        retry_history=[
            RetryHistoryResponse(
                attempt_number=r.attempt_number,
                attempted_at=r.attempted_at,
                failure_reason=r.failure_reason,
                error_details=r.error_details
            )
            for r in entry.retry_history
        ],
        last_failure_reason=entry.last_failure_reason,
        dlq_reason=entry.dlq_reason or "Unknown",
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        first_attempted_at=entry.first_attempted_at,
        completed_at=entry.completed_at
    )


@router.get("/campaigns/{campaign_id}/queue", response_model=QueueSummaryResponse)
async def get_campaign_queue_status(
    campaign_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get queue status with summary statistics for a campaign.

    Returns counts for each queue state (pending, calling, success, failed, etc.)
    """
    # Verify campaign exists
    from backend.app.services.campaign_service import CampaignService
    campaign = await CampaignService.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found"
        )

    summary = await QueueService.get_campaign_queue_summary(campaign_id)

    return QueueSummaryResponse(**summary)


@router.get("/campaigns/{campaign_id}/queue/entries", response_model=QueueListResponse)
async def list_campaign_queue_entries(
    campaign_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    state: Optional[QueueState] = None,
    current_user: User = Depends(get_current_user)
):
    """
    List queue entries for a campaign with filtering.

    Query parameters:
    - state: Filter by queue state
    - skip: Pagination offset (default 0)
    - limit: Max results (default 50, max 100)
    """
    # Verify campaign exists
    from backend.app.services.campaign_service import CampaignService
    campaign = await CampaignService.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found"
        )

    entries, total = await QueueService.list_campaign_queue(
        campaign_id=campaign_id,
        skip=skip,
        limit=limit,
        state=state
    )

    return QueueListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[queue_entry_to_response(entry) for entry in entries]
    )


@router.get("/queue/dlq", response_model=DLQListResponse)
async def list_dlq_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    campaign_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    List Dead Letter Queue entries for review.

    Admin-only endpoint.

    Query parameters:
    - campaign_id: Filter by campaign (optional)
    - skip: Pagination offset (default 0)
    - limit: Max results (default 50, max 100)
    """
    # Require Admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for DLQ access"
        )

    entries, total = await QueueService.list_dlq_entries(
        skip=skip,
        limit=limit,
        campaign_id=campaign_id
    )

    return DLQListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[queue_entry_to_dlq_response(entry) for entry in entries]
    )


@router.post("/queue/dlq/{entry_id}/retry", response_model=QueueEntryResponse)
async def retry_dlq_entry(
    entry_id: str,
    request: DLQRetryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Manually retry a DLQ entry.

    Admin-only endpoint.

    Moves the entry back to PENDING state and optionally resets retry count.
    """
    # Require Admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for DLQ retry"
        )

    try:
        entry = await QueueService.retry_dlq_entry(
            entry_id=entry_id,
            reset_retry_count=request.reset_retry_count
        )

        logger.info(
            f"Admin {current_user.email} manually retried DLQ entry {entry_id}"
        )

        return queue_entry_to_response(entry)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/queue/dlq/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dlq_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Permanently remove a DLQ entry.

    Admin-only endpoint.

    WARNING: This action is irreversible.
    """
    # Require Admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for DLQ deletion"
        )

    try:
        await QueueService.delete_dlq_entry(entry_id)

        logger.info(
            f"Admin {current_user.email} permanently deleted DLQ entry {entry_id}"
        )

        return None

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/queue/stats", response_model=GlobalQueueStatsResponse)
async def get_global_queue_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get global queue statistics across all campaigns.

    Admin-only endpoint.

    Returns:
    - Total campaigns active
    - Queue entry counts by state
    - Average retry count
    - DLQ rate percentage
    """
    # Require Admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for global stats"
        )

    stats = await QueueService.get_global_queue_stats()

    return GlobalQueueStatsResponse(**stats)
