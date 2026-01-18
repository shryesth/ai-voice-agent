"""
Celery task for initiating patient feedback voice calls.

Integrates:
- Twilio call initiation
- CallRecord creation
- Pipeline state updates
"""

from celery import Task
from backend.app.celery_app import celery_app, get_worker_event_loop
from backend.app.domains.patient_feedback.twilio_integration import TwilioIntegration
from backend.app.services.call_service import CallService
from backend.app.models.call_record import CallOutcome
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def get_or_create_event_loop():
    """Get existing event loop or create a new one if needed."""
    try:
        loop = asyncio.get_running_loop()
        return loop
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop


class VoiceCallTask(Task):
    """Base task for voice call operations with retry logic"""
    
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True
    max_retries = 3


@celery_app.task(base=VoiceCallTask, bind=True, name="initiate_patient_call")
def initiate_patient_call(
    self,
    campaign_id: str,
    patient_phone: str,
    language: str = "en",
    status_callback_url: str = None
):
    """
    Initiate outbound call to patient.

    This task:
    1. Creates CallRecord in database
    2. Initiates Twilio outbound call
    3. Call connects to WebSocket endpoint for voice pipeline
    4. Updates CallRecord with Twilio metadata

    Args:
        campaign_id: Campaign ID
        patient_phone: Patient phone number (E.164 format)
        language: Language preference (en, es, fr, ht)
        status_callback_url: URL for Twilio status callbacks

    Returns:
        Dict with call_record_id and call_sid
    """
    logger.info(f"Initiating call to {patient_phone} for campaign {campaign_id}")

    try:
        # 1. Create CallRecord
        loop = get_worker_event_loop()
        call_record = loop.run_until_complete(CallService.create_call_record(
            campaign_id=campaign_id,
            patient_phone=patient_phone,
            language=language
        ))

        # 2. Initialize Twilio integration
        twilio = TwilioIntegration()

        # 3. Initiate Twilio call
        # The call will connect to the WebSocket endpoint which runs the voice pipeline
        call_data = twilio.initiate_call(
            to_number=patient_phone,
            campaign_id=campaign_id,
            patient_phone=patient_phone,
            language=language,
            status_callback_url=status_callback_url
        )

        # 4. Update CallRecord with Twilio metadata
        call_record.call_tracking.call_sid = call_data["call_sid"]
        call_record.call_tracking.status = call_data["status"]
        call_record.call_tracking.created_at = datetime.utcnow()
        loop.run_until_complete(call_record.save())

        logger.info(f"Call initiated: {call_data['call_sid']} for record {call_record.id}")

        return {
            "call_record_id": str(call_record.id),
            "call_sid": call_data["call_sid"],
            "status": call_data["status"]
        }

    except Exception as e:
        logger.error(f"Failed to initiate call: {e}", exc_info=True)
        
        # Update call record with error
        if 'call_record' in locals():
            call_record.error_message = str(e)
            call_record.call_tracking.outcome = CallOutcome.FAILED
            loop = get_worker_event_loop()
            loop.run_until_complete(call_record.save())
        
        raise


@celery_app.task(name="update_call_from_webhook")
def update_call_from_webhook(call_sid: str, status: str, duration: int = None):
    """
    Update CallRecord from Twilio status webhook.

    Args:
        call_sid: Twilio Call SID
        status: Call status (initiated, ringing, answered, completed, etc.)
        duration: Call duration in seconds (for completed calls)

    Returns:
        Dict with call_record_id and updated status
    """
    logger.info(f"Updating call {call_sid} with status {status}")

    try:
        loop = get_worker_event_loop()
        
        # Find call record by Twilio SID
        call_record = loop.run_until_complete(CallService.get_call_by_twilio_sid(call_sid))
        
        if not call_record:
            logger.warning(f"Call record not found for Twilio SID: {call_sid}")
            return None

        # Update status
        call_record.call_tracking.status = status

        # Handle status-specific updates
        if status == "ringing":
            # Call is ringing
            pass
        elif status == "in-progress" or status == "answered":
            call_record.call_tracking.started_at = datetime.utcnow()
        elif status == "completed":
            call_record.call_tracking.ended_at = datetime.utcnow()
            if duration:
                call_record.call_tracking.duration_seconds = int(duration)
            # Don't override outcome if pipeline already set it
            if not call_record.call_tracking.outcome:
                call_record.call_tracking.outcome = CallOutcome.SUCCESS
        elif status in ["busy", "no-answer", "failed", "canceled"]:
            call_record.call_tracking.ended_at = datetime.utcnow()
            if status == "busy":
                call_record.call_tracking.outcome = CallOutcome.BUSY
            elif status == "no-answer":
                call_record.call_tracking.outcome = CallOutcome.NO_ANSWER
            else:
                call_record.call_tracking.outcome = CallOutcome.FAILED

        call_record.updated_at = datetime.utcnow()
        loop.run_until_complete(call_record.save())

        logger.info(f"Updated call record {call_record.id} with status {status}")

        return {
            "call_record_id": str(call_record.id),
            "status": status
        }

    except Exception as e:
        logger.error(f"Failed to update call from webhook: {e}", exc_info=True)
        raise
