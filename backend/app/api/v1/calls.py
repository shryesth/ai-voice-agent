"""
API routes for patient feedback call management.

Endpoints:
- GET /api/v1/calls/{id} - Get call record by ID
- GET /api/v1/campaigns/{id}/calls - List campaign calls
- GET /api/v1/calls/urgent - List urgent-flagged calls
- POST /api/v1/webhooks/twilio/status - Twilio status webhook
- POST /api/v1/campaigns/{id}/calls/test - Initiate test call (future)
- WebSocket /api/v1/webhooks/twilio/media - Twilio media stream
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, WebSocket, WebSocketDisconnect, Query, Form
from fastapi.responses import StreamingResponse, Response
from typing import Optional
import io
import logging
from bson import ObjectId

from backend.app.models.user import User, UserRole
from backend.app.models.call_record import CallOutcome, CallRecord
from backend.app.schemas.call import (
    CallRecordResponse,
    CallListResponse,
    ConversationStateResponse,
    FeedbackDataResponse,
    CallTrackingResponse,
    ConversationTurnResponse,
    RecordingMetadataResponse,
    TestCallRequest,
    TestCallResponse,
    TestScenarioRequest,
    SplitRecordingResponse
)
from backend.app.services.call_service import CallService
from backend.app.services.recording_service import RecordingService
from backend.app.api.v1.auth import get_current_user
from backend.app.domains.patient_feedback.twilio_integration import TwilioIntegration
from backend.app.core.config import settings
from twilio.request_validator import RequestValidator
from backend.app.domains.patient_feedback.voice_pipeline import create_voice_pipeline
from backend.app.tasks.voice_call import update_call_from_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


def call_to_response(call, user_role: Optional[UserRole] = None) -> CallRecordResponse:
    """Convert CallRecord to CallRecordResponse schema"""
    # Privacy: Hide patient_phone from User role
    patient_phone = call.patient_phone if user_role != UserRole.USER else "[REDACTED]"
    
    return CallRecordResponse(
        id=str(call.id),
        campaign_id=str(call.campaign_id),
        patient_phone=patient_phone,
        language=call.language,
        conversation_state=ConversationStateResponse(
            current_stage=call.conversation_state.current_stage,
            completed_stages=call.conversation_state.completed_stages,
            failed_stages=call.conversation_state.failed_stages,
            stage_retry_counts=call.conversation_state.stage_retry_counts
        ),
        transcript=[
            ConversationTurnResponse(
                speaker=turn.speaker,
                text=turn.text,
                timestamp=turn.timestamp,
                language=turn.language
            )
            for turn in call.transcript
        ],
        feedback=FeedbackDataResponse(
            overall_satisfaction=call.feedback.overall_satisfaction,
            specific_concerns=call.feedback.specific_concerns,
            side_effects_reported=call.feedback.side_effects_reported,
            experience_quality=call.feedback.experience_quality
        ),
        urgency_flagged=call.urgency_flagged,
        urgency_keywords_detected=call.urgency_keywords_detected,
        call_tracking=CallTrackingResponse(
            call_sid=call.call_tracking.call_sid,
            stream_sid=call.call_tracking.stream_sid,
            status=call.call_tracking.status,
            outcome=call.call_tracking.outcome,
            created_at=call.call_tracking.created_at,
            started_at=call.call_tracking.started_at,
            ended_at=call.call_tracking.ended_at,
            duration_seconds=call.call_tracking.duration_seconds
        ),
        recording=RecordingMetadataResponse(
            recording_url=call.recording.recording_url,
            s3_object_key=call.recording.s3_object_key,
            duration_seconds=call.recording.duration_seconds,
            file_size_bytes=call.recording.file_size_bytes,
            sample_rate=call.recording.sample_rate,
            num_channels=call.recording.num_channels,
            uploaded_at=call.recording.uploaded_at
        ) if call.recording else None,
        error_message=call.error_message,
        created_at=call.created_at,
        updated_at=call.updated_at
    )


@router.post("/campaigns/{campaign_id}/calls/test", response_model=TestCallResponse, status_code=status.HTTP_202_ACCEPTED)
async def initiate_test_call(
    campaign_id: str,
    request: TestCallRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Initiate test call to verify voice pipeline before launching campaign.

    Admin-only endpoint. Test calls bypass the queue and are initiated immediately.

    Performance: Must respond < 10 seconds (SC-004)
    """
    # Require Admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for test calls"
        )

    # Verify campaign exists
    from backend.app.services.campaign_service import CampaignService
    campaign = await CampaignService.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found"
        )

    # Initiate test call
    result = await CallService.initiate_test_call(
        campaign_id=campaign_id,
        phone_number=request.phone_number,
        language=request.language
    )

    return TestCallResponse(**result)


@router.post("/campaigns/{campaign_id}/calls/test-scenario", response_model=TestCallResponse, status_code=status.HTTP_202_ACCEPTED)
async def initiate_test_scenario(
    campaign_id: str,
    request: TestScenarioRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Simulate test conversation with specific scenario path (for debugging).

    Admin-only endpoint. Scenarios:
    - happy_path: Full conversation, success
    - wrong_person: Caller not patient/guardian
    - urgent_keywords: Simulate urgency detection
    - network_failure: Simulate mid-call disconnect
    - short_duration: Simulate <30s call
    """
    # Require Admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for test scenarios"
        )

    # Verify campaign exists
    from backend.app.services.campaign_service import CampaignService
    campaign = await CampaignService.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found"
        )

    # Simulate scenario
    result = await CallService.simulate_scenario(
        campaign_id=campaign_id,
        phone_number=request.phone_number,
        scenario=request.scenario,
        language=request.language,
        scenario_params=request.scenario_params
    )

    return TestCallResponse(**result)


@router.get("/calls/urgent", response_model=CallListResponse)
async def list_urgent_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """
    List all urgent-flagged calls for clinical review.

    Returns calls where urgency_flagged=true, sorted by most recent.
    """
    calls, total = await CallService.list_urgent_calls(
        skip=skip,
        limit=limit
    )

    return CallListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[call_to_response(call, user_role=current_user.role) for call in calls]
    )


@router.get("/calls/{call_id}", response_model=CallRecordResponse)
async def get_call_record(
    call_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get call record by ID with full transcript.

    Privacy: patient_phone is redacted for User role.
    """
    call = await CallService.get_call_by_id(call_id, user_role=current_user.role)

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record {call_id} not found"
        )

    return call_to_response(call, user_role=current_user.role)


@router.get("/campaigns/{campaign_id}/calls", response_model=CallListResponse)
async def list_campaign_calls(
    campaign_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    outcome: Optional[CallOutcome] = None,
    urgency_flagged: Optional[bool] = None,
    current_user: User = Depends(get_current_user)
):
    """
    List all calls for a campaign with filtering.

    Query parameters:
    - outcome: Filter by call outcome
    - urgency_flagged: Filter by urgency flag (true/false)
    - skip: Pagination offset (default 0)
    - limit: Max results (default 50, max 100)
    """
    calls, total = await CallService.list_campaign_calls(
        campaign_id=campaign_id,
        skip=skip,
        limit=limit,
        outcome=outcome,
        urgency_flagged=urgency_flagged,
        user_role=current_user.role
    )

    return CallListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[call_to_response(call, user_role=current_user.role) for call in calls]
    )


@router.post("/webhooks/twilio/status")
async def twilio_status_webhook(request: Request):
    """
    Twilio status callback webhook.
    
    Receives call status updates from Twilio:
    - initiated, ringing, answered, in-progress, completed, busy, no-answer, failed
    
    Validates Twilio signature for security.
    """
    # Get form data
    form_data = await request.form()
    params = dict(form_data)

    # Validate Twilio signature (skip in development with ngrok)
    # ngrok changes URLs which breaks Twilio signature validation
    twilio = TwilioIntegration()
    if not settings.is_development:
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)

        if not twilio.validate_webhook(url, params, signature):
            logger.warning(f"Invalid Twilio signature for webhook: {url}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio signature"
            )
    else:
        logger.debug("Skipping Twilio signature validation in development mode")
    
    # Parse status data
    status_data = twilio.parse_status_callback(params)
    
    # Update call record asynchronously via Celery
    update_call_from_webhook.delay(
        call_sid=status_data["call_sid"],
        status=status_data["call_status"],
        duration=status_data.get("call_duration")
    )
    
    logger.info(f"Twilio status webhook processed: {status_data['call_sid']} - {status_data['call_status']}")

    return {"status": "ok"}


@router.post("/webhooks/twilio/recording", include_in_schema=False)
async def twilio_recording_callback(
    request: Request,
    CallSid: str = Form(...),
    RecordingSid: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingStatus: str = Form(...),
    RecordingDuration: str = Form(...),
):
    """
    Webhook called by Twilio when recording is complete.
    Downloads recording from Twilio and uploads to MinIO.
    """
    logger.info(f"📼 Recording callback - CallSid: {CallSid}, RecordingSid: {RecordingSid}")
    logger.info(f"   Status: {RecordingStatus}, Duration: {RecordingDuration}s")

    # Validate Twilio signature (skip in development with ngrok)
    # ngrok changes URLs which breaks Twilio signature validation
    if not settings.is_development:
        validator = RequestValidator(settings.twilio_auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")

        form_data = await request.form()
        url = str(request.url)

        if not validator.validate(url, dict(form_data), signature):
            logger.warning(f"⚠️ Invalid Twilio signature for recording callback: {url}")
            raise HTTPException(status_code=403, detail="Invalid signature")
    else:
        logger.info("⚠️ Skipping Twilio signature validation in development mode")

    # Only process completed recordings
    if RecordingStatus != "completed":
        logger.warning(f"⚠️ Recording not completed: {RecordingStatus}")
        return Response(status_code=200)

    # Check if recording is enabled
    if not settings.recording_enabled:
        logger.warning("⚠️ Recording disabled, skipping download")
        return Response(status_code=200)

    # Trigger async task to download and store recording
    from backend.app.tasks.recording_download import download_twilio_recording

    download_twilio_recording.delay(
        call_sid=CallSid,
        recording_sid=RecordingSid,
        recording_url=RecordingUrl,
        recording_duration=int(RecordingDuration),
    )

    logger.info(f"✅ Queued recording download task for call: {CallSid}")
    return Response(status_code=200)


@router.websocket("/webhooks/twilio/media")
async def twilio_media_stream(websocket: WebSocket):
    """
    Twilio Media Stream WebSocket endpoint for voice calls.
    
    Twilio connects to this endpoint when outbound call is answered.
    The WebSocket receives µ-law 8kHz audio and sends back synthesized audio.
    
    Flow:
    1. Receive Twilio "start" event with call metadata
    2. Create CallRecord in database
    3. Run Pipecat voice pipeline (blocks until call completes)
    4. Update CallRecord with final conversation state
    """
    await websocket.accept()

    try:
        # 1. Wait for Twilio events (connected, then start)
        start_message = None
        
        while start_message is None:
            message = await websocket.receive_json()
            event_type = message.get("event")
            
            logger.info(f"Received Twilio event: {event_type}")
            
            if event_type == "connected":
                logger.info("Twilio WebSocket connected")
                continue
            elif event_type == "start":
                start_message = message
                break
            else:
                logger.error(f"Unexpected event from Twilio: {event_type}, message: {message}")
                await websocket.close()
                return

        # Extract call metadata
        twilio = TwilioIntegration()
        call_data = twilio.parse_media_stream_start(start_message)

        call_sid = call_data["call_sid"]
        stream_sid = call_data["stream_sid"]
        campaign_id = call_data.get("campaign_id")
        patient_phone = call_data.get("patient_phone")
        language = call_data.get("language", "en")
        call_record_id = call_data.get("call_record_id")  # Get from Twilio parameters

        logger.info(f"Twilio media stream started: {call_sid}")

        # 2. Get existing CallRecord by ID (passed through Twilio parameters)
        call_record = None
        if call_record_id:
            try:
                call_record = await CallRecord.get(call_record_id)
            except Exception as e:
                logger.warning(f"Could not find CallRecord with ID {call_record_id}: {e}")
        
        if not call_record:
            # Fallback: try to find by call_sid or create new
            call_record = await CallService.get_call_by_twilio_sid(call_sid)
            
        if not call_record:
            # Last resort: create new CallRecord if not found
            logger.warning(f"CallRecord not found for call_sid {call_sid}, creating new one")
            call_record = await CallService.create_call_record(
                campaign_id=campaign_id,
                patient_phone=patient_phone,
                language=language
            )
        
        # Update with Twilio metadata
        call_record.call_tracking.call_sid = call_sid
        
        # Update with stream metadata
        call_record.call_tracking.stream_sid = stream_sid
        call_record.call_tracking.status = "in-progress"
        await call_record.save()

        # 3. Prepare call_data for pipeline
        pipeline_call_data = {
            "call_sid": call_sid,
            "stream_sid": stream_sid,
            "campaign_id": campaign_id,
            "patient_phone": patient_phone,
            "language": language
        }

        # 4. Run Pipecat voice pipeline (blocks until call completes)
        final_state = await create_voice_pipeline(
            websocket=websocket,
            call_record_id=str(call_record.id),
            call_data=pipeline_call_data,
            call_record=call_record  # Pass call_record for real-time transcript updates
        )

        # 5. Update CallRecord with final conversation state
        await CallService.update_call_from_pipeline_state(
            call_id=str(call_record.id),
            pipeline_state=final_state
        )

        logger.info(f"Call completed successfully: {call_sid}")

    except WebSocketDisconnect:
        logger.info(f"Twilio WebSocket disconnected: {call_sid if 'call_sid' in locals() else 'unknown'}")
    except Exception as e:
        logger.error(f"Error in voice pipeline: {e}", exc_info=True)
        # Update CallRecord with error state
        if 'call_record' in locals():
            call_record.call_tracking.status = "failed"
            call_record.error_message = str(e)
            call_record.call_tracking.outcome = CallOutcome.FAILED
            await call_record.save()
    finally:
        try:
            await websocket.close()
        except:
            pass


@router.get("/campaigns/{campaign_id}/calls/export")
async def export_campaign_calls_csv(
    campaign_id: str,
    outcome: Optional[CallOutcome] = None,
    urgency_flagged: Optional[bool] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Export campaign calls to CSV format.
    
    Admin-only endpoint for data export.
    """
    # Require Admin role
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for CSV export"
        )
    
    csv_data = await CallService.export_calls_csv(
        campaign_id=campaign_id,
        outcome=outcome,
        urgency_flagged=urgency_flagged
    )
    
    # Return as streaming CSV response
    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_calls.csv"}
    )


@router.post(
    "/{call_id}/split-recording",
    response_model=SplitRecordingResponse,
    summary="Split dual-channel recording into caller/callee/mixed tracks"
)
async def split_recording(
    call_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Split dual-channel recording into separate tracks (lazy + cache).

    - Downloads dual-channel MP3 from MinIO
    - Splits into: caller-only, callee-only, mixed-mono
    - Uploads all 3 to MinIO
    - Caches S3 keys in CallRecord
    - Returns presigned URLs for all tracks

    If already split, returns cached URLs immediately.
    """
    logger.info(f"Splitting recording for call: {call_id}")

    # Get call record
    try:
        call_record = await CallRecord.get(ObjectId(call_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Call record not found")

    if not call_record:
        raise HTTPException(status_code=404, detail="Call record not found")

    # Check if recording exists
    if not call_record.recording or not call_record.recording.s3_object_key:
        raise HTTPException(status_code=404, detail="No recording found for this call")

    # Check if already split (cache hit)
    if (call_record.recording.caller_s3_key and
        call_record.recording.callee_s3_key and
        call_record.recording.mixed_s3_key):
        logger.info(f"Recording already split, returning cached URLs")

        # Generate presigned URLs
        recording_service = RecordingService()
        return SplitRecordingResponse(
            caller_url=await recording_service.get_presigned_url(
                call_record.recording.caller_s3_key
            ),
            callee_url=await recording_service.get_presigned_url(
                call_record.recording.callee_s3_key
            ),
            mixed_url=await recording_service.get_presigned_url(
                call_record.recording.mixed_s3_key
            ),
            dual_url=await recording_service.get_presigned_url(
                call_record.recording.s3_object_key
            ),
            split_created_at=call_record.recording.split_created_at,
            status="completed"
        )

    # Cache miss - trigger split task
    from backend.app.tasks.split_recording import split_recording_task

    task = split_recording_task.delay(call_id=call_id)

    logger.info(f"Queued split task {task.id} for call: {call_id}")

    return SplitRecordingResponse(
        task_id=task.id,
        status="processing",
        message=f"Recording split in progress. Poll /api/v1/calls/{call_id} for status.",
    )
