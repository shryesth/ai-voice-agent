"""
Queue Management Router

Simplified endpoints for programmatic queue integration.
Handles webhook callbacks and status synchronization for managed queues.
"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.models.queue_models import (
    CallEntryStatus,
    FailureReason,
    QueueState,
)
from backend.app.infrastructure.database.queue_repository import (
    get_queue_repository,
    get_call_entry_repository,
)
from backend.app.services.queue.scheduler import get_queue_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/queue-mgmt",
    tags=["Queue Management"],
    responses={
        500: {"description": "Internal server error"},
    }
)


# Request/Response Models

class CallStatusUpdate(BaseModel):
    """Status update from Twilio or internal system"""
    entry_id: str = Field(..., description="Call entry ID")
    call_sid: Optional[str] = Field(None, description="Twilio call SID")
    status: str = Field(..., description="Call status (completed, busy, no-answer, failed, canceled)")
    duration: Optional[int] = Field(None, description="Call duration in seconds")
    error_code: Optional[str] = Field(None, description="Error code if failed")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class CallStatusResponse(BaseModel):
    """Response for status update"""
    success: bool
    entry_id: str
    new_status: str
    message: str
    retry_scheduled: Optional[bool] = None
    retry_at: Optional[str] = None


class QueueHealthResponse(BaseModel):
    """Queue system health check response"""
    healthy: bool
    active_queues: int
    total_pending_calls: int
    total_calling_now: int
    message: str


class QueueSummary(BaseModel):
    """Simplified queue summary"""
    queue_id: str
    name: str
    state: str
    pending: int
    calling: int
    completed: int
    failed: int


# Helper functions

def _map_twilio_status_to_failure_reason(status: str, error_code: Optional[str] = None) -> Optional[FailureReason]:
    """Map Twilio call status to FailureReason"""
    status_lower = status.lower()

    if status_lower == "completed":
        return None  # Success, not a failure
    elif status_lower == "busy":
        return FailureReason.BUSY
    elif status_lower in ("no-answer", "no_answer"):
        return FailureReason.NO_ANSWER
    elif status_lower == "canceled":
        return FailureReason.REJECTED
    elif status_lower == "failed":
        # Check error codes for specific failure types
        if error_code:
            # Invalid number codes
            if error_code in ("21211", "21214", "21217"):
                return FailureReason.INVALID_NUMBER
        return FailureReason.FAILED
    else:
        return FailureReason.FAILED


# Endpoints

@router.post(
    "/status-callback",
    response_model=CallStatusResponse,
    summary="Handle call status callback",
    description="""
    **Webhook endpoint for call status updates**

    Called by Twilio or internal system when a call status changes.
    Automatically handles retry scheduling based on failure reason.

    ## Status Values
    - **completed**: Call was answered and completed
    - **busy**: Line was busy
    - **no-answer**: Call was not answered
    - **failed**: Call failed (check error_code)
    - **canceled**: Call was canceled
    """
)
async def status_callback(update: CallStatusUpdate):
    """Handle call status callback and update managed queue entry"""
    try:
        scheduler = get_queue_scheduler()
        call_entry_repo = get_call_entry_repository()

        # Get the entry
        entry = await call_entry_repo.get_entry(update.entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Entry {update.entry_id} not found")

        status_lower = update.status.lower()

        if status_lower == "completed":
            # Check duration for short call validation
            if update.duration is not None and update.duration < 30:
                # Short call - treat as failure
                success = await scheduler.handle_call_failure(
                    entry_id=update.entry_id,
                    failure_reason=FailureReason.SHORT_DURATION,
                    failure_details=f"Call duration {update.duration}s is less than 30s minimum",
                    call_duration=update.duration
                )

                # Get updated entry for retry info
                updated_entry = await call_entry_repo.get_entry(update.entry_id)
                retry_scheduled = updated_entry and updated_entry.status == CallEntryStatus.RETRY_SCHEDULED

                return CallStatusResponse(
                    success=success,
                    entry_id=update.entry_id,
                    new_status="retry_scheduled" if retry_scheduled else "dead_letter",
                    message=f"Short call ({update.duration}s) - {'retry scheduled' if retry_scheduled else 'moved to DLQ'}",
                    retry_scheduled=retry_scheduled,
                    retry_at=updated_entry.scheduled_for.isoformat() if retry_scheduled and updated_entry.scheduled_for else None
                )

            # Successful call
            success = await scheduler.handle_call_success(
                entry_id=update.entry_id,
                call_sid=update.call_sid or "",
                call_duration=update.duration
            )

            return CallStatusResponse(
                success=success,
                entry_id=update.entry_id,
                new_status="success",
                message="Call completed successfully"
            )

        else:
            # Failed call - determine failure reason
            failure_reason = _map_twilio_status_to_failure_reason(
                update.status,
                update.error_code
            )

            if failure_reason:
                failure_details = update.error_message or f"Call status: {update.status}"
                if update.error_code:
                    failure_details = f"[{update.error_code}] {failure_details}"

                success = await scheduler.handle_call_failure(
                    entry_id=update.entry_id,
                    failure_reason=failure_reason,
                    failure_details=failure_details,
                    call_duration=update.duration
                )

                # Get updated entry for retry info
                updated_entry = await call_entry_repo.get_entry(update.entry_id)
                retry_scheduled = updated_entry and updated_entry.status == CallEntryStatus.RETRY_SCHEDULED

                return CallStatusResponse(
                    success=success,
                    entry_id=update.entry_id,
                    new_status="retry_scheduled" if retry_scheduled else "dead_letter",
                    message=f"Call failed ({failure_reason.value}) - {'retry scheduled' if retry_scheduled else 'moved to DLQ'}",
                    retry_scheduled=retry_scheduled,
                    retry_at=updated_entry.scheduled_for.isoformat() if retry_scheduled and updated_entry.scheduled_for else None
                )

            return CallStatusResponse(
                success=False,
                entry_id=update.entry_id,
                new_status="unknown",
                message=f"Unknown status: {update.status}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling status callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health",
    response_model=QueueHealthResponse,
    summary="Queue system health check",
    description="Check the health of the managed queue system"
)
async def health_check():
    """Get queue system health status"""
    try:
        queue_repo = get_queue_repository()
        call_entry_repo = get_call_entry_repository()

        # Get all queues
        queues = await queue_repo.list_queues()
        active_queues = len([q for q in queues if q.state == QueueState.ACTIVE])

        # Get aggregate stats
        total_pending = 0
        total_calling = 0

        for queue in queues:
            if queue.state == QueueState.ACTIVE:
                pending = await call_entry_repo.count_pending(queue.queue_id)
                calling = await call_entry_repo.count_calling_now(queue.queue_id)
                total_pending += pending
                total_calling += calling

        healthy = True
        message = "Queue system is healthy"

        if active_queues == 0 and total_pending > 0:
            healthy = False
            message = "Pending calls but no active queues"

        return QueueHealthResponse(
            healthy=healthy,
            active_queues=active_queues,
            total_pending_calls=total_pending,
            total_calling_now=total_calling,
            message=message
        )

    except Exception as e:
        logger.error(f"Error checking queue health: {e}")
        return QueueHealthResponse(
            healthy=False,
            active_queues=0,
            total_pending_calls=0,
            total_calling_now=0,
            message=f"Health check failed: {str(e)}"
        )


@router.get(
    "/queues/summary",
    response_model=list[QueueSummary],
    summary="Get queue summaries",
    description="Get a simplified summary of all managed queues"
)
async def get_queue_summaries(
    state: Optional[str] = Query(None, description="Filter by state (active, paused, completed, cancelled)")
):
    """Get simplified queue summaries for monitoring"""
    try:
        queue_repo = get_queue_repository()
        call_entry_repo = get_call_entry_repository()

        queues = await queue_repo.list_queues()

        # Filter by state if specified
        if state:
            try:
                filter_state = QueueState(state.lower())
                queues = [q for q in queues if q.state == filter_state]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid state: {state}. Must be one of: active, paused, completed, cancelled"
                )

        summaries = []
        for queue in queues:
            stats = await call_entry_repo.get_queue_statistics(queue.queue_id, queue.name)

            summaries.append(QueueSummary(
                queue_id=queue.queue_id,
                name=queue.name,
                state=queue.state.value,
                pending=stats.pending_calls if stats else 0,
                calling=stats.calling_now if stats else 0,
                completed=stats.successful_calls if stats else 0,
                failed=stats.failed_calls if stats else 0
            ))

        return summaries

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue summaries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/process-retries",
    summary="Trigger retry processing",
    description="Manually trigger processing of scheduled retries"
)
async def process_retries():
    """Manually trigger processing of retry-scheduled calls"""
    try:
        scheduler = get_queue_scheduler()
        processed = await scheduler.process_ready_retries()

        return {
            "success": True,
            "processed_count": processed,
            "message": f"Processed {processed} retry-scheduled calls"
        }

    except Exception as e:
        logger.error(f"Error processing retries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/entry/{entry_id}/status",
    summary="Get call entry status",
    description="Get the current status of a managed queue call entry"
)
async def get_entry_status(entry_id: str):
    """Get the current status of a call entry"""
    try:
        call_entry_repo = get_call_entry_repository()
        entry = await call_entry_repo.get_entry(entry_id)

        if not entry:
            raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

        return {
            "entry_id": entry.entry_id,
            "queue_id": entry.queue_id,
            "phone_number": entry.phone_number,
            "status": entry.status.value,
            "retry_count": entry.retry_count,
            "call_sid": entry.call_sid,
            "call_duration": entry.call_duration,
            "failure_reason": entry.failure_reason.value if entry.failure_reason else None,
            "failure_details": entry.failure_details,
            "scheduled_for": entry.scheduled_for.isoformat() if entry.scheduled_for else None,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "last_updated": entry.last_updated.isoformat() if entry.last_updated else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting entry status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
