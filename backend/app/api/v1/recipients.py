"""
Recipient API endpoints.

Provides CRUD operations and management for queue recipients.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId

from backend.app.models.enums import RecipientStatus, UserRole
from backend.app.models.recipient import Recipient
from backend.app.services.recipient_service import recipient_service
from backend.app.schemas.recipient import (
    RecipientCreate,
    RecipientUpdate,
    RecipientBulkCreate,
    RecipientResponse,
    RecipientListResponse,
    RecipientTimelineResponse,
    RecipientSummaryResponse,
    DLQListResponse,
    DLQRetryRequest,
    SkipRecipientRequest,
    CallAttemptSchema,
    recipient_to_response,
)
from backend.app.api.v1.auth import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recipients", tags=["recipients"])


@router.post(
    "/queues/{queue_id}/recipients",
    response_model=RecipientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_recipient(
    queue_id: str,
    data: RecipientCreate,
    current_user=Depends(require_admin),
):
    """
    Create a new recipient in a queue.

    Admin only.
    """
    try:
        recipient = await recipient_service.create_recipient(
            queue_id=queue_id,
            contact_phone=data.contact_phone,
            contact_name=data.contact_name,
            contact_type=data.contact_type,
            language=data.language,
            patient_name=data.patient_name,
            patient_relation=data.patient_relation,
            patient_age=data.patient_age,
            priority=data.priority,
            event_info=data.event_info.model_dump() if data.event_info else None,
        )
        return recipient_to_response(recipient, current_user.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/queues/{queue_id}/recipients/bulk",
    response_model=RecipientListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_recipients_bulk(
    queue_id: str,
    data: RecipientBulkCreate,
    current_user=Depends(require_admin),
):
    """
    Bulk create recipients in a queue.

    Admin only.
    """
    created = []
    errors = []

    for item in data.recipients:
        try:
            recipient = await recipient_service.create_recipient(
                queue_id=queue_id,
                contact_phone=item.contact_phone,
                contact_name=item.contact_name,
                contact_type=item.contact_type,
                language=item.language,
                patient_name=item.patient_name,
                patient_relation=item.patient_relation,
                patient_age=item.patient_age,
                priority=item.priority,
            )
            created.append(recipient)
        except ValueError as e:
            errors.append(f"{item.contact_phone}: {str(e)}")

    if errors:
        logger.warning(f"Bulk create had {len(errors)} errors: {errors}")

    return RecipientListResponse(
        items=[recipient_to_response(r, current_user.role) for r in created],
        total=len(created),
        skip=0,
        limit=len(created),
    )


@router.get("/queues/{queue_id}/recipients", response_model=RecipientListResponse)
async def list_recipients(
    queue_id: str,
    status_filter: Optional[RecipientStatus] = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """
    List recipients in a queue.
    """
    recipients = await recipient_service.list_recipients(
        queue_id=queue_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )

    total = len(recipients)  # TODO: Add proper count query

    return RecipientListResponse(
        items=[recipient_to_response(r, current_user.role) for r in recipients],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{recipient_id}", response_model=RecipientResponse)
async def get_recipient(
    recipient_id: str,
    current_user=Depends(get_current_user),
):
    """
    Get a recipient by ID.
    """
    recipient = await recipient_service.get_recipient_by_id(recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return recipient_to_response(recipient, current_user.role)


@router.patch("/{recipient_id}", response_model=RecipientResponse)
async def update_recipient(
    recipient_id: str,
    data: RecipientUpdate,
    current_user=Depends(require_admin),
):
    """
    Update a recipient.

    Admin only.
    """
    recipient = await recipient_service.get_recipient_by_id(recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    # Apply updates
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if hasattr(recipient, key):
            setattr(recipient, key, value)

    recipient.updated_at = datetime.utcnow()
    await recipient.save()

    return recipient_to_response(recipient, current_user.role)


@router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipient(
    recipient_id: str,
    current_user=Depends(require_admin),
):
    """
    Delete a recipient (only if pending).

    Admin only.
    """
    recipient = await recipient_service.get_recipient_by_id(recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    if recipient.status not in (RecipientStatus.PENDING, RecipientStatus.SKIPPED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete recipient in status: {recipient.status.value}",
        )

    await recipient.delete()


@router.get("/{recipient_id}/timeline", response_model=RecipientTimelineResponse)
async def get_recipient_timeline(
    recipient_id: str,
    current_user=Depends(get_current_user),
):
    """
    Get the call attempt timeline for a recipient.
    """
    try:
        timeline = await recipient_service.get_timeline(recipient_id)
        recipient = await recipient_service.get_recipient_by_id(recipient_id)

        # Privacy filtering
        contact_phone = recipient.contact_phone
        if current_user.role == UserRole.USER:
            if contact_phone and len(contact_phone) > 4:
                contact_phone = contact_phone[:3] + "****" + contact_phone[-2:]

        return RecipientTimelineResponse(
            recipient_id=str(recipient.id),
            contact_phone=contact_phone,
            contact_name=recipient.contact_name,
            status=recipient.status.value,
            timeline=[CallAttemptSchema(**t) for t in timeline],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{recipient_id}/skip", response_model=RecipientResponse)
async def skip_recipient(
    recipient_id: str,
    data: SkipRecipientRequest = None,
    current_user=Depends(require_admin),
):
    """
    Skip a recipient (mark as SKIPPED).

    Admin only.
    """
    try:
        reason = data.reason if data else None
        recipient = await recipient_service.skip_recipient(recipient_id, reason)
        return recipient_to_response(recipient, current_user.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# DLQ endpoints
@router.get("/dlq", response_model=DLQListResponse)
async def list_dlq(
    queue_id: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user=Depends(require_admin),
):
    """
    List recipients in Dead Letter Queue.

    Admin only.
    """
    recipients = await recipient_service.list_dlq(
        queue_id=queue_id,
        skip=skip,
        limit=limit,
    )

    total = len(recipients)

    return DLQListResponse(
        items=[recipient_to_response(r, current_user.role) for r in recipients],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/dlq/{recipient_id}/retry", response_model=RecipientResponse)
async def retry_dlq_recipient(
    recipient_id: str,
    data: DLQRetryRequest = None,
    current_user=Depends(require_admin),
):
    """
    Retry a recipient from DLQ.

    Admin only.
    """
    try:
        reset = data.reset_retry_count if data else False
        recipient = await recipient_service.retry_from_dlq(recipient_id, reset)
        return recipient_to_response(recipient, current_user.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/dlq/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dlq_recipient(
    recipient_id: str,
    current_user=Depends(require_admin),
):
    """
    Permanently delete a DLQ recipient.

    Admin only.
    """
    recipient = await recipient_service.get_recipient_by_id(recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    if recipient.status != RecipientStatus.DLQ:
        raise HTTPException(
            status_code=400,
            detail="Recipient is not in DLQ",
        )

    await recipient.delete()


@router.get("/queues/{queue_id}/summary", response_model=RecipientSummaryResponse)
async def get_recipient_summary(
    queue_id: str,
    current_user=Depends(get_current_user),
):
    """
    Get summary statistics for queue recipients.
    """
    # Count by status
    by_status = {}
    total = 0

    for status in RecipientStatus:
        count = await Recipient.find(
            Recipient.queue_id.id == ObjectId(queue_id),
            Recipient.status == status,
        ).count()
        by_status[status.value] = count
        total += count

    # Count urgent
    urgent_count = await Recipient.find(
        Recipient.queue_id.id == ObjectId(queue_id),
        Recipient.urgency_flagged == True,
    ).count()

    # Count callback requested
    callback_count = await Recipient.find(
        Recipient.queue_id.id == ObjectId(queue_id),
        Recipient.human_callback_requested == True,
    ).count()

    return RecipientSummaryResponse(
        queue_id=queue_id,
        total=total,
        by_status=by_status,
        urgent_count=urgent_count,
        callback_requested_count=callback_count,
    )
