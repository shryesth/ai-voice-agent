"""
Test Call API endpoints.

Provides endpoints for:
- One-off test calls
- Active test call management
- Queue debugging
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId

from backend.app.models.enums import (
    CallType,
    ContactType,
    CallOutcome,
    QueueState,
    RecipientStatus,
)
from backend.app.models.geography import Geography
from backend.app.models.call_queue import CallQueue
from backend.app.models.call_record import CallRecord, CallTracking, ConversationState
from backend.app.models.recipient import Recipient
from backend.app.services.call_queue_service import call_queue_service
from backend.app.services.recipient_service import recipient_service
from backend.app.schemas.test_call import (
    TestCallRequest,
    TestCallResponse,
    ActiveTestCallResponse,
    ActiveTestCallListResponse,
    CancelTestCallResponse,
    QueueDebugResponse,
    ForceProcessRequest,
    ForceProcessResponse,
    SyncClarityRequest,
    SyncClarityResponse,
    TriggerCallRequest,
    TriggerCallResponse,
)
from backend.app.api.v1.auth import get_current_user, require_admin
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test-calls", tags=["test-calls"])


@router.post("/initiate", response_model=TestCallResponse)
async def initiate_test_call(
    data: TestCallRequest,
    current_user=Depends(require_admin),
):
    """
    Initiate a one-off test call.

    Creates a CallRecord marked as test call and initiates the call
    through Twilio. Does not create a queue or recipient.

    IMPORTANT: event_info is REQUIRED - it provides context for the AI conversation
    including what service was provided, when, and where.

    Admin only.
    """
    # Verify geography exists
    geography = await Geography.get(ObjectId(data.geography_id))
    if not geography:
        raise HTTPException(status_code=404, detail="Geography not found")

    # Convert event_info to dict for storage
    event_info_dict = data.event_info.model_dump()

    # Create CallRecord for test call with full event context
    call_record = CallRecord(
        geography_id=str(geography.id),
        call_type=data.call_type,
        contact_phone=data.phone_number,
        contact_name=data.contact_name,
        contact_type=data.contact_type,
        language=data.language,
        patient_name=data.patient_name,
        guardian_relation=data.guardian_relation,
        event_info=event_info_dict,
        greeting_template=data.greeting_template,
        is_test_call=True,
        conversation_state=ConversationState(),
        call_tracking=CallTracking(status="initiated"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await call_record.insert()

    # Initiate call via Celery task
    try:
        from backend.app.tasks.voice_call import initiate_patient_call

        # Build status callback URL
        status_callback_url = f"{settings.public_url}/api/v1/webhooks/twilio/status"

        # Queue the call task
        task = initiate_patient_call.delay(
            campaign_id=None,  # No campaign for test calls
            patient_phone=data.phone_number,
            language=data.language,
            status_callback_url=status_callback_url,
            call_record_id=str(call_record.id),
            is_test_call=True,
        )

        logger.info(f"Initiated test call {call_record.id} to {data.phone_number}")

        return TestCallResponse(
            call_id=str(call_record.id),
            call_sid=None,  # Will be set when Twilio responds
            status="initiated",
            phone_number=data.phone_number,
            language=data.language,
            call_type=data.call_type.value,
            is_test_call=True,
            created_at=call_record.created_at,
        )

    except Exception as e:
        logger.error(f"Failed to initiate test call: {e}")
        call_record.call_tracking.status = "failed"
        call_record.error_message = str(e)
        await call_record.save()
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {e}")


@router.get("/active", response_model=ActiveTestCallListResponse)
async def list_active_test_calls(
    current_user=Depends(require_admin),
):
    """
    List currently active test calls.

    Admin only.
    """
    # Find test calls that are not in terminal state
    active_calls = await CallRecord.find(
        CallRecord.is_test_call == True,
        CallRecord.call_tracking.status.in_(["initiated", "ringing", "in-progress"]),
    ).sort("-created_at").limit(50).to_list()

    items = []
    for call in active_calls:
        items.append(ActiveTestCallResponse(
            call_id=str(call.id),
            call_sid=call.call_tracking.call_sid if call.call_tracking else None,
            phone_number=call.contact_phone,
            status=call.call_tracking.status if call.call_tracking else None,
            call_type=call.call_type.value,
            language=call.language,
            duration_seconds=call.call_tracking.duration_seconds if call.call_tracking else None,
            started_at=call.call_tracking.started_at if call.call_tracking else None,
            current_stage=call.conversation_state.current_stage,
        ))

    return ActiveTestCallListResponse(
        items=items,
        total=len(items),
    )


@router.delete("/{call_id}", response_model=CancelTestCallResponse)
async def cancel_test_call(
    call_id: str,
    current_user=Depends(require_admin),
):
    """
    Cancel an active test call.

    Admin only.
    """
    call_record = await CallRecord.get(ObjectId(call_id))
    if not call_record:
        raise HTTPException(status_code=404, detail="Call not found")

    if not call_record.is_test_call:
        raise HTTPException(status_code=400, detail="Not a test call")

    if call_record.call_tracking and call_record.call_tracking.status in ("completed", "failed", "canceled"):
        raise HTTPException(status_code=400, detail="Call already ended")

    # Cancel via Twilio if we have a call_sid
    if call_record.call_tracking and call_record.call_tracking.call_sid:
        try:
            from twilio.rest import Client

            twilio_client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
            )
            twilio_client.calls(call_record.call_tracking.call_sid).update(
                status="canceled"
            )
        except Exception as e:
            logger.warning(f"Failed to cancel Twilio call: {e}")

    # Update call record
    if call_record.call_tracking:
        call_record.call_tracking.status = "canceled"
        call_record.call_tracking.ended_at = datetime.utcnow()
    call_record.updated_at = datetime.utcnow()
    await call_record.save()

    return CancelTestCallResponse(
        call_id=str(call_record.id),
        status="canceled",
        message="Test call canceled",
    )


# Debug endpoints
@router.get("/queues/{queue_id}/debug", response_model=QueueDebugResponse)
async def get_queue_debug(
    queue_id: str,
    current_user=Depends(require_admin),
):
    """
    Get debug information for a queue.

    Admin only.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    # Check time window
    from backend.app.tasks.queue_processor import is_within_time_window

    is_within = is_within_time_window(queue.time_windows)

    # Get recipient counts
    pending = await Recipient.find(
        Recipient.queue_id.id == ObjectId(queue_id),
        Recipient.status == RecipientStatus.PENDING,
    ).count()

    calling = await Recipient.find(
        Recipient.queue_id.id == ObjectId(queue_id),
        Recipient.status == RecipientStatus.CALLING,
    ).count()

    retrying = await Recipient.find(
        Recipient.queue_id.id == ObjectId(queue_id),
        Recipient.status == RecipientStatus.RETRYING,
    ).count()

    # Get recent failures
    recent_failures = await Recipient.find(
        Recipient.queue_id.id == ObjectId(queue_id),
        Recipient.status.in_([RecipientStatus.FAILED, RecipientStatus.NOT_REACHABLE]),
    ).sort("-updated_at").limit(10).to_list()

    failure_list = [
        {
            "recipient_id": str(r.id),
            "phone": r.contact_phone[-4:],  # Last 4 digits only
            "status": r.status.value,
            "failure_reason": r.last_failure_reason.value if r.last_failure_reason else None,
            "retry_count": r.retry_count,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in recent_failures
    ]

    return QueueDebugResponse(
        queue_id=str(queue.id),
        name=queue.name,
        state=queue.state.value,
        mode=queue.mode.value,
        is_within_time_window=is_within,
        current_time_utc=datetime.utcnow().strftime("%H:%M"),
        time_windows=[tw.model_dump() for tw in queue.time_windows],
        clarity_sync_enabled=queue.clarity_sync.enabled,
        last_clarity_sync=queue.clarity_sync.last_sync_at.isoformat() if queue.clarity_sync.last_sync_at else None,
        pending_recipients=pending,
        calling_recipients=calling,
        retrying_recipients=retrying,
        recent_failures=failure_list,
    )


@router.post("/queues/{queue_id}/force-process", response_model=ForceProcessResponse)
async def force_process_queue(
    queue_id: str,
    data: ForceProcessRequest = None,
    current_user=Depends(require_admin),
):
    """
    Force process queue entries (bypass time windows).

    Admin only.
    """
    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    if queue.state != QueueState.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Queue is not active: {queue.state.value}")

    max_count = data.max_recipients if data else 5

    # Get ready recipients
    recipients = await recipient_service.get_ready_recipients(queue_id, max_count)

    if not recipients:
        return ForceProcessResponse(
            queue_id=queue_id,
            processed_count=0,
            call_ids=[],
            message="No recipients ready for processing",
        )

    # Process each recipient
    from backend.app.tasks.voice_call import initiate_patient_call

    call_ids = []
    for recipient in recipients:
        try:
            # Create call record
            call_record = CallRecord(
                geography_id=str(queue.geography_id.id),
                queue_id=str(queue.id),
                recipient_id=str(recipient.id),
                call_type=queue.call_type,
                contact_phone=recipient.contact_phone,
                contact_name=recipient.contact_name,
                contact_type=recipient.contact_type,
                language=recipient.language,
                patient_name=recipient.patient_name,
                conversation_state=ConversationState(),
                call_tracking=CallTracking(status="initiated"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            await call_record.insert()

            # Mark recipient as calling
            await recipient_service.mark_calling(str(recipient.id), str(call_record.id))

            # Queue the call
            status_callback_url = f"{settings.public_url}/api/v1/webhooks/twilio/status"
            initiate_patient_call.delay(
                campaign_id=str(queue.id),
                patient_phone=recipient.contact_phone,
                language=recipient.language,
                status_callback_url=status_callback_url,
                call_record_id=str(call_record.id),
            )

            call_ids.append(str(call_record.id))

        except Exception as e:
            logger.error(f"Failed to process recipient {recipient.id}: {e}")

    return ForceProcessResponse(
        queue_id=queue_id,
        processed_count=len(call_ids),
        call_ids=call_ids,
        message=f"Processed {len(call_ids)} recipients",
    )


@router.post("/queues/{queue_id}/sync-clarity", response_model=SyncClarityResponse)
async def sync_clarity(
    queue_id: str,
    data: SyncClarityRequest = None,
    current_user=Depends(require_admin),
):
    """
    Force Clarity sync for a queue.

    Admin only.
    """
    from backend.app.services.clarity_service import get_clarity_service

    queue = await call_queue_service.get_queue_by_id(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    direction = data.direction if data else "both"
    max_count = data.max_count if data else 100

    # Get Clarity service
    geography = await Geography.get(queue.geography_id.id)
    if not geography or not geography.clarity_config.enabled:
        raise HTTPException(status_code=400, detail="Clarity not configured for this geography")

    clarity_service = await get_clarity_service(str(geography.id))
    if not clarity_service:
        raise HTTPException(status_code=400, detail="Failed to initialize Clarity service")

    pulled_count = 0
    pushed_count = 0
    errors = []

    # Pull from Clarity
    if direction in ("pull", "both"):
        try:
            recipients = await clarity_service.pull_verification_subjects(
                queue=queue,
                max_count=max_count,
                event_type_filter=queue.clarity_sync.event_type_filter,
            )
            pulled_count = len(recipients)
        except Exception as e:
            errors.append(f"Pull failed: {e}")

    # Push to Clarity
    if direction in ("push", "both"):
        try:
            # Find completed recipients not yet synced
            completed = await Recipient.find(
                Recipient.queue_id.id == ObjectId(queue_id),
                Recipient.status.in_([
                    RecipientStatus.COMPLETED,
                    RecipientStatus.FAILED,
                    RecipientStatus.NOT_REACHABLE,
                ]),
                Recipient.sync_status == "pending",
            ).limit(max_count).to_list()

            for recipient in completed:
                try:
                    await clarity_service.push_verification_result(recipient)
                    pushed_count += 1
                except Exception as e:
                    errors.append(f"Push failed for {recipient.id}: {e}")

        except Exception as e:
            errors.append(f"Push query failed: {e}")

    return SyncClarityResponse(
        queue_id=queue_id,
        direction=direction,
        pulled_count=pulled_count,
        pushed_count=pushed_count,
        errors=errors,
        message=f"Pulled {pulled_count}, pushed {pushed_count}",
    )


@router.post("/recipients/{recipient_id}/trigger-call", response_model=TriggerCallResponse)
async def trigger_recipient_call(
    recipient_id: str,
    data: TriggerCallRequest = None,
    current_user=Depends(require_admin),
):
    """
    Manually trigger a call for a specific recipient.

    Admin only.
    """
    recipient = await recipient_service.get_recipient_by_id(recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    if recipient.status not in (RecipientStatus.PENDING, RecipientStatus.RETRYING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot trigger call for recipient in status: {recipient.status.value}",
        )

    # Get queue
    queue = await CallQueue.get(recipient.queue_id.id)
    if not queue:
        raise HTTPException(status_code=400, detail="Queue not found")

    # Create call record
    call_record = CallRecord(
        geography_id=str(queue.geography_id.id),
        queue_id=str(queue.id),
        recipient_id=str(recipient.id),
        call_type=queue.call_type,
        contact_phone=recipient.contact_phone,
        contact_name=recipient.contact_name,
        contact_type=recipient.contact_type,
        language=recipient.language,
        patient_name=recipient.patient_name,
        conversation_state=ConversationState(),
        call_tracking=CallTracking(status="initiated"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await call_record.insert()

    # Mark recipient as calling
    await recipient_service.mark_calling(str(recipient.id), str(call_record.id))

    # Queue the call
    try:
        from backend.app.tasks.voice_call import initiate_patient_call

        status_callback_url = f"{settings.public_url}/api/v1/webhooks/twilio/status"
        initiate_patient_call.delay(
            campaign_id=str(queue.id),
            patient_phone=recipient.contact_phone,
            language=recipient.language,
            status_callback_url=status_callback_url,
            call_record_id=str(call_record.id),
        )

        return TriggerCallResponse(
            recipient_id=recipient_id,
            call_record_id=str(call_record.id),
            status="initiated",
            message="Call initiated",
        )

    except Exception as e:
        logger.error(f"Failed to trigger call: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger call: {e}")
