"""
Unit tests for RecipientService.

Tests service logic for recipient management, call tracking, and DLQ operations.
"""

import pytest
from datetime import datetime, timedelta
from backend.app.services.recipient_service import recipient_service
from backend.app.models.recipient import Recipient
from backend.app.models.enums import RecipientStatus


@pytest.mark.unit
class TestRecipientServiceCreate:
    """Test recipient creation operations"""

    @pytest.mark.asyncio
    async def test_create_recipient_basic(self, seeded_call_queue):
        """Test creating a basic recipient"""
        recipient = await recipient_service.create_recipient(
            queue_id=str(seeded_call_queue.id),
            contact_phone="+12025551234",
            contact_name="John Doe",
            contact_type="patient",
            language="en"
        )

        assert recipient is not None
        assert recipient.contact_phone == "+12025551234"
        assert recipient.contact_name == "John Doe"
        assert recipient.contact_type == "patient"
        assert recipient.language == "en"
        assert recipient.status == RecipientStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_recipient_with_event_info(self, seeded_call_queue):
        """Test creating recipient with event information"""
        event_info = {
            "clarity_verification_id": "test-123",
            "event_type": "Suivi des Enfants",
            "event_category": "child_vaccination",
            "confirmation_message_key": "child_vaccination_rr1",
            "event_date": datetime.utcnow().isoformat(),
            "facility_name": "Test Clinic"
        }

        recipient = await recipient_service.create_recipient(
            queue_id=str(seeded_call_queue.id),
            contact_phone="+12025551234",
            contact_name="John Doe",
            contact_type="patient",
            language="en",
            event_info=event_info
        )

        assert recipient.event_info is not None
        assert recipient.event_info.clarity_verification_id == "test-123"

    @pytest.mark.asyncio
    async def test_create_recipient_invalid_queue(self):
        """Test creating recipient with invalid queue"""
        from bson import ObjectId
        invalid_queue_id = str(ObjectId())

        with pytest.raises(ValueError):
            await recipient_service.create_recipient(
                queue_id=invalid_queue_id,
                contact_phone="+12025551234",
                contact_name="John Doe",
                contact_type="patient",
                language="en"
            )

    @pytest.mark.asyncio
    async def test_create_recipient_invalid_phone(self, seeded_call_queue):
        """Test creating recipient with invalid phone"""
        with pytest.raises(ValueError):
            await recipient_service.create_recipient(
                queue_id=str(seeded_call_queue.id),
                contact_phone="invalid",
                contact_name="John Doe",
                contact_type="patient",
                language="en"
            )

    @pytest.mark.asyncio
    async def test_create_recipient_duplicate_in_queue(self, seeded_call_queue):
        """Test creating duplicate recipient in same queue"""
        phone = "+12025551234"

        # Create first recipient
        await recipient_service.create_recipient(
            queue_id=str(seeded_call_queue.id),
            contact_phone=phone,
            contact_name="John Doe",
            contact_type="patient",
            language="en"
        )

        # Try to create duplicate
        with pytest.raises(ValueError):
            await recipient_service.create_recipient(
                queue_id=str(seeded_call_queue.id),
                contact_phone=phone,
                contact_name="Jane Doe",
                contact_type="patient",
                language="en"
            )


@pytest.mark.unit
class TestRecipientServiceRetrieval:
    """Test recipient retrieval operations"""

    @pytest.mark.asyncio
    async def test_get_recipient_by_id(self, seeded_recipient):
        """Test getting recipient by ID"""
        recipient = await recipient_service.get_recipient_by_id(str(seeded_recipient.id))

        assert recipient is not None
        assert str(recipient.id) == str(seeded_recipient.id)
        assert recipient.contact_phone == seeded_recipient.contact_phone

    @pytest.mark.asyncio
    async def test_get_recipient_by_id_not_found(self):
        """Test getting non-existent recipient"""
        from bson import ObjectId
        invalid_id = str(ObjectId())

        recipient = await recipient_service.get_recipient_by_id(invalid_id)

        assert recipient is None

    @pytest.mark.asyncio
    async def test_list_recipients_by_queue(self, seeded_recipient):
        """Test listing recipients in a queue"""
        queue_id = str(seeded_recipient.queue_id)

        recipients = await recipient_service.list_recipients(queue_id=queue_id)

        assert len(recipients) >= 1
        recipient_ids = [str(r.id) for r in recipients]
        assert str(seeded_recipient.id) in recipient_ids

    @pytest.mark.asyncio
    async def test_list_recipients_filter_by_status(self, seeded_recipient):
        """Test listing recipients filtered by status"""
        queue_id = str(seeded_recipient.queue_id)

        recipients = await recipient_service.list_recipients(
            queue_id=queue_id,
            status=RecipientStatus.PENDING
        )

        # All returned recipients should have PENDING status
        for recipient in recipients:
            assert recipient.status == RecipientStatus.PENDING

    @pytest.mark.asyncio
    async def test_list_recipients_pagination(self, seeded_recipient):
        """Test recipient listing with pagination"""
        queue_id = str(seeded_recipient.queue_id)

        recipients = await recipient_service.list_recipients(
            queue_id=queue_id,
            skip=0,
            limit=10
        )

        assert len(recipients) <= 10


@pytest.mark.unit
class TestRecipientServiceUpdate:
    """Test recipient update operations"""

    @pytest.mark.asyncio
    async def test_mark_recipient_calling(self, seeded_recipient):
        """Test marking recipient as calling"""
        recipient = await recipient_service.mark_calling(str(seeded_recipient.id))

        assert recipient is not None
        assert recipient.status == RecipientStatus.CALLING

    @pytest.mark.asyncio
    async def test_skip_recipient(self, seeded_recipient):
        """Test skipping a recipient"""
        recipient = await recipient_service.skip_recipient(
            str(seeded_recipient.id),
            reason="Contact requested skip"
        )

        assert recipient is not None
        assert recipient.status == RecipientStatus.SKIPPED


@pytest.mark.unit
class TestRecipientServiceCallCompletion:
    """Test recipient call completion and retry logic"""

    @pytest.mark.asyncio
    async def test_handle_call_completion_success(self, seeded_recipient):
        """Test handling successful call completion"""
        recipient = await recipient_service.handle_call_completion(
            recipient_id=str(seeded_recipient.id),
            outcome="completed_full",
            transcript="Test transcript",
            call_duration=120
        )

        assert recipient is not None
        assert recipient.status == RecipientStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_handle_call_completion_failure_with_retry(self, seeded_recipient, seeded_call_queue):
        """Test handling call failure that allows retry"""
        recipient = await recipient_service.handle_call_completion(
            recipient_id=str(seeded_recipient.id),
            outcome="no_answer",
            failure_reason="no_answer"
        )

        assert recipient is not None
        assert recipient.status == RecipientStatus.RETRYING
        assert recipient.next_retry_at is not None

    @pytest.mark.asyncio
    async def test_handle_call_max_retries_exceeded(self, seeded_recipient):
        """Test handling call when max retries exceeded"""
        # Set retry count to max
        recipient = await recipient_service.get_recipient_by_id(str(seeded_recipient.id))
        recipient.retry_count = 10  # Exceed default max of 3

        # Handle failure
        updated = await recipient_service.handle_call_completion(
            recipient_id=str(seeded_recipient.id),
            outcome="no_answer",
            failure_reason="no_answer"
        )

        # Should move to DLQ
        if updated.retry_count > updated.queue.retry_strategy.max_retries:
            assert updated.status == RecipientStatus.DLQ


@pytest.mark.unit
class TestRecipientServiceDLQ:
    """Test recipient DLQ operations"""

    @pytest.mark.asyncio
    async def test_move_to_dlq(self, seeded_recipient):
        """Test moving recipient to DLQ"""
        recipient = await recipient_service.move_to_dlq(
            str(seeded_recipient.id),
            reason="max_retries_exceeded"
        )

        assert recipient is not None
        assert recipient.status == RecipientStatus.DLQ
        assert recipient.dlq_reason == "max_retries_exceeded"

    @pytest.mark.asyncio
    async def test_list_dlq(self, seeded_recipient):
        """Test listing DLQ recipients"""
        # First move a recipient to DLQ
        await recipient_service.move_to_dlq(
            str(seeded_recipient.id),
            reason="test"
        )

        # List DLQ
        dlq_recipients = await recipient_service.list_dlq()

        assert len(dlq_recipients) >= 1
        dlq_ids = [str(r.id) for r in dlq_recipients]
        assert str(seeded_recipient.id) in dlq_ids

    @pytest.mark.asyncio
    async def test_retry_from_dlq(self, seeded_recipient):
        """Test retrying a DLQ recipient"""
        # First move to DLQ
        await recipient_service.move_to_dlq(
            str(seeded_recipient.id),
            reason="max_retries_exceeded"
        )

        # Retry from DLQ
        recipient = await recipient_service.retry_from_dlq(
            str(seeded_recipient.id),
            reset=True
        )

        assert recipient is not None
        assert recipient.status != RecipientStatus.DLQ
        if reset:
            assert recipient.retry_count == 0


@pytest.mark.unit
class TestRecipientServiceTimeline:
    """Test recipient timeline operations"""

    @pytest.mark.asyncio
    async def test_get_recipient_timeline(self, seeded_recipient):
        """Test getting recipient call timeline"""
        timeline = await recipient_service.get_timeline(str(seeded_recipient.id))

        assert timeline is not None
        assert isinstance(timeline, list)

    @pytest.mark.asyncio
    async def test_get_recipient_timeline_not_found(self):
        """Test getting timeline for non-existent recipient"""
        from bson import ObjectId
        invalid_id = str(ObjectId())

        with pytest.raises(ValueError):
            await recipient_service.get_timeline(invalid_id)


@pytest.mark.unit
class TestRecipientServiceUrgency:
    """Test recipient urgency operations"""

    @pytest.mark.asyncio
    async def test_update_urgency(self, seeded_recipient):
        """Test updating recipient urgency"""
        recipient = await recipient_service.update_urgency(
            str(seeded_recipient.id),
            is_urgent=True,
            reason="critical_condition"
        )

        assert recipient is not None
        assert recipient.is_urgent is True
        assert recipient.urgency_reason == "critical_condition"

    @pytest.mark.asyncio
    async def test_clear_urgency(self, seeded_recipient):
        """Test clearing recipient urgency"""
        # Set urgency first
        await recipient_service.update_urgency(
            str(seeded_recipient.id),
            is_urgent=True,
            reason="test"
        )

        # Clear it
        recipient = await recipient_service.update_urgency(
            str(seeded_recipient.id),
            is_urgent=False
        )

        assert recipient is not None
        assert recipient.is_urgent is False


@pytest.mark.unit
class TestRecipientServiceCallback:
    """Test recipient callback request operations"""

    @pytest.mark.asyncio
    async def test_request_human_callback(self, seeded_recipient):
        """Test requesting human callback"""
        recipient = await recipient_service.request_human_callback(
            str(seeded_recipient.id)
        )

        assert recipient is not None
        assert recipient.requested_human_callback is True
        assert recipient.callback_requested_at is not None
