"""
CallService for managing patient feedback call records.

Handles:
- Call record creation and updates
- Query calls by campaign, outcome, urgency
- Export calls to CSV
- Privacy filtering for User role
"""

from typing import List, Optional
from datetime import datetime, timezone
import csv
import io
from beanie import PydanticObjectId
from beanie.operators import In, Eq

from backend.app.core.config import settings
from backend.app.models.call_record import CallRecord, CallOutcome
from backend.app.models.campaign import Campaign
from backend.app.models.user import UserRole
import logging

logger = logging.getLogger(__name__)


class CallService:
    """Service layer for call record operations"""

    @staticmethod
    async def create_call_record(
        campaign_id: str,
        patient_phone: str,
        language: str = "en"
    ) -> CallRecord:
        """
        Create new call record.

        Args:
            campaign_id: Campaign ID
            patient_phone: Patient phone number (E.164 format)
            language: Language preference

        Returns:
            Created CallRecord
        """
        call_record = CallRecord(
            campaign_id=campaign_id,
            patient_phone=patient_phone,
            language=language
        )
        await call_record.save()
        logger.info(f"Created call record {call_record.id} for campaign {campaign_id}")
        return call_record

    @staticmethod
    async def get_call_by_id(
        call_id: str,
        user_role: Optional[UserRole] = None
    ) -> Optional[CallRecord]:
        """
        Get call record by ID.

        Args:
            call_id: Call record ID
            user_role: User role (for privacy filtering)

        Returns:
            CallRecord or None if not found
        """
        call = await CallRecord.get(PydanticObjectId(call_id))
        
        # Privacy: Hide patient_phone from User role
        if call and user_role == UserRole.USER:
            call.patient_phone = "[REDACTED]"
        
        return call

    @staticmethod
    async def get_call_by_twilio_sid(call_sid: str) -> Optional[CallRecord]:
        """
        Get call record by Twilio Call SID.

        Args:
            call_sid: Twilio Call SID

        Returns:
            CallRecord or None
        """
        return await CallRecord.find_one(
            CallRecord.call_tracking.call_sid == call_sid
        )

    @staticmethod
    async def list_campaign_calls(
        campaign_id: str,
        skip: int = 0,
        limit: int = 50,
        outcome: Optional[CallOutcome] = None,
        urgency_flagged: Optional[bool] = None,
        user_role: Optional[UserRole] = None
    ) -> tuple[List[CallRecord], int]:
        """
        List calls for a campaign with filtering.

        Args:
            campaign_id: Campaign ID
            skip: Pagination offset
            limit: Max results
            outcome: Filter by call outcome
            urgency_flagged: Filter by urgency flag
            user_role: User role (for privacy filtering)

        Returns:
            Tuple of (calls list, total count)
        """
        # Build query
        query = CallRecord.find(CallRecord.campaign_id == campaign_id)
        
        if outcome:
            query = query.find(CallRecord.call_tracking.outcome == outcome)
        
        if urgency_flagged is not None:
            query = query.find(CallRecord.urgency_flagged == urgency_flagged)
        
        # Get total count
        total = await query.count()
        
        # Get paginated results
        calls = await query.sort("-created_at").skip(skip).limit(limit).to_list()
        
        # Privacy: Hide patient_phone from User role
        if user_role == UserRole.USER:
            for call in calls:
                call.patient_phone = "[REDACTED]"
        
        return calls, total

    @staticmethod
    async def list_urgent_calls(
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[CallRecord], int]:
        """
        List all urgent-flagged calls (for clinical review).

        Args:
            skip: Pagination offset
            limit: Max results

        Returns:
            Tuple of (calls list, total count)
        """
        query = CallRecord.find(CallRecord.urgency_flagged == True)
        
        total = await query.count()
        calls = await query.sort("-created_at").skip(skip).limit(limit).to_list()
        
        return calls, total

    @staticmethod
    async def update_call_from_pipeline_state(
        call_id: str,
        pipeline_state: dict
    ) -> CallRecord:
        """
        Update call record with final pipeline state.

        Args:
            call_id: Call record ID
            pipeline_state: FlowManager state from voice pipeline

        Returns:
            Updated CallRecord
        """
        call = await CallRecord.get(PydanticObjectId(call_id))
        if not call:
            raise ValueError(f"Call record {call_id} not found")

        # Update conversation state from FlowManager state
        # FlowManager uses: completed_stages, current_stage, *_retry_count, etc.
        if "completed_stages" in pipeline_state:
            call.conversation_state.completed_stages = pipeline_state["completed_stages"]

        if "current_stage" in pipeline_state:
            call.conversation_state.current_stage = pipeline_state["current_stage"]

        # Update stage retry counts
        stage_retry_counts = {}
        if pipeline_state.get("guardian_retry_count"):
            stage_retry_counts["confirm_guardian"] = pipeline_state["guardian_retry_count"]
        if pipeline_state.get("visit_retry_count"):
            stage_retry_counts["confirm_visit"] = pipeline_state["visit_retry_count"]
        if stage_retry_counts:
            call.conversation_state.stage_retry_counts = stage_retry_counts

        # Update feedback data from FlowManager fields
        if "satisfaction_rating" in pipeline_state:
            call.feedback.overall_satisfaction = pipeline_state["satisfaction_rating"]

        if "has_side_effects" in pipeline_state:
            call.feedback.side_effects_reported = pipeline_state.get("side_effects_details", "")

        # Update urgency flags
        if pipeline_state.get("urgency_flagged") or pipeline_state.get("severe_side_effects"):
            call.urgency_flagged = True
            call.urgency_keywords_detected = pipeline_state.get("urgency_keywords", [])

        # Update completion status
        if pipeline_state.get("completed"):
            if not call.conversation_state.current_stage:
                call.conversation_state.current_stage = "completed"
            call.call_tracking.outcome = CallOutcome.SUCCESS

        # Store completion reason
        if "completion_reason" in pipeline_state:
            # Store in error_message if it's an abnormal completion
            if pipeline_state["completion_reason"] not in ["complete"]:
                call.error_message = f"Call ended: {pipeline_state['completion_reason']}"

        # Update error if present
        if "error" in pipeline_state:
            call.error_message = pipeline_state["error"]
            call.call_tracking.outcome = CallOutcome.FAILED

        call.updated_at = datetime.now(timezone.utc)
        await call.save()

        logger.info(f"Updated call {call_id} from pipeline state: {list(pipeline_state.keys())}")

        # Queue translation for non-English completed calls
        if (
            call.language != "en"
            and pipeline_state.get("completed")
            and getattr(settings, "translation_enabled", True)
        ):
            try:
                from backend.app.tasks.transcript_translation import translate_transcript
                translate_transcript.delay(str(call.id))
                logger.info(f"Queued translation task for non-English call: {call.id}")
            except Exception as e:
                logger.warning(f"Failed to queue translation task: {e}")

        # Trigger recipient sync task to transfer CallRecord data to Recipient
        # This enables bidirectional Clarity sync
        if call.recipient_id:
            try:
                from backend.app.tasks.recipient_sync import sync_recipient_from_call
                sync_recipient_from_call.delay(str(call.id))
                logger.info(f"Queued recipient sync for CallRecord {call.id}")
            except Exception as e:
                logger.warning(f"Failed to queue recipient sync task: {e}")

        return call

    @staticmethod
    async def export_calls_csv(
        campaign_id: Optional[str] = None,
        outcome: Optional[CallOutcome] = None,
        urgency_flagged: Optional[bool] = None
    ) -> str:
        """
        Export calls to CSV format.

        Args:
            campaign_id: Filter by campaign (optional)
            outcome: Filter by outcome (optional)
            urgency_flagged: Filter by urgency (optional)

        Returns:
            CSV string
        """
        # Build query
        query = CallRecord.find()
        
        if campaign_id:
            query = query.find(CallRecord.campaign_id == campaign_id)
        if outcome:
            query = query.find(CallRecord.call_tracking.outcome == outcome)
        if urgency_flagged is not None:
            query = query.find(CallRecord.urgency_flagged == urgency_flagged)
        
        calls = await query.to_list()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Call ID",
            "Campaign ID",
            "Patient Phone",
            "Language",
            "Call SID",
            "Outcome",
            "Duration (s)",
            "Satisfaction",
            "Concerns",
            "Side Effects",
            "Urgency Flagged",
            "Urgency Keywords",
            "Created At",
            "Started At",
            "Ended At"
        ])
        
        # Data rows
        for call in calls:
            writer.writerow([
                str(call.id),
                str(call.campaign_id),
                call.patient_phone,
                call.language,
                call.call_tracking.call_sid or "",
                call.call_tracking.outcome or "",
                call.call_tracking.duration_seconds or "",
                call.feedback.overall_satisfaction or "",
                call.feedback.specific_concerns or "",
                call.feedback.side_effects_reported or "",
                "Yes" if call.urgency_flagged else "No",
                ", ".join(call.urgency_keywords_detected) if call.urgency_keywords_detected else "",
                call.created_at.isoformat() if call.created_at else "",
                call.call_tracking.started_at.isoformat() if call.call_tracking.started_at else "",
                call.call_tracking.ended_at.isoformat() if call.call_tracking.ended_at else ""
            ])
        
        return output.getvalue()

    @staticmethod
    async def initiate_test_call(
        campaign_id: str,
        phone_number: str,
        language: str = "en"
    ) -> dict:
        """
        Initiate test call for campaign validation.

        Test calls bypass the queue and are initiated immediately.

        Args:
            campaign_id: Campaign ID
            phone_number: Phone number to call (E.164 format)
            language: Language preference

        Returns:
            Dict with call_id, status, message
        """
        from backend.app.tasks.voice_call import initiate_patient_call

        # Create call record
        call_record = await CallService.create_call_record(
            campaign_id=campaign_id,
            patient_phone=phone_number,
            language=language
        )

        # Initiate call immediately (bypass queue)
        task_result = initiate_patient_call.delay(
            campaign_id=campaign_id,
            patient_phone=phone_number,
            language=language
        )

        logger.info(f"Test call initiated: {call_record.id}")

        return {
            "call_id": str(call_record.id),
            "status": "queued",
            "phone_number": phone_number,
            "language": language,
            "message": f"Test call queued. Check status at /api/v1/calls/{call_record.id}"
        }

    @staticmethod
    async def simulate_scenario(
        campaign_id: str,
        phone_number: str,
        scenario: str,
        language: str = "en",
        scenario_params: dict = None
    ) -> dict:
        """
        Simulate test call with specific scenario.

        This creates a test call record with scenario metadata for debugging.

        Args:
            campaign_id: Campaign ID
            phone_number: Phone number
            scenario: Scenario name (happy_path, wrong_person, etc.)
            language: Language preference
            scenario_params: Additional scenario parameters

        Returns:
            Dict with call_id, status, scenario, message
        """
        # Create call record with scenario metadata
        call_record = await CallService.create_call_record(
            campaign_id=campaign_id,
            patient_phone=phone_number,
            language=language
        )

        # Store scenario in error_message field for tracking
        # (In production, you'd add a dedicated scenario field to CallRecord)
        call_record.error_message = f"Test scenario: {scenario}"
        await call_record.save()

        # Initiate call
        from backend.app.tasks.voice_call import initiate_patient_call
        initiate_patient_call.delay(
            campaign_id=campaign_id,
            patient_phone=phone_number,
            language=language
        )

        logger.info(f"Test scenario '{scenario}' initiated: {call_record.id}")

        return {
            "call_id": str(call_record.id),
            "status": "queued",
            "scenario": scenario,
            "phone_number": phone_number,
            "language": language,
            "message": f"Test scenario '{scenario}' queued for execution"
        }
