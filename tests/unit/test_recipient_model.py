"""
Unit tests for Recipient model.

Tests model logic including status validation, retry scheduling, and DLQ criteria.
"""

import pytest
from datetime import datetime, timedelta
from backend.app.models.recipient import Recipient, ClarityEventInfo, CallAttempt
from backend.app.models.enums import RecipientStatus, CallOutcome, ContactType, FailureReason


@pytest.mark.unit
class TestRecipientStatusValidation:
    """Test Recipient status values and transitions"""

    def test_recipient_default_status_pending(self, seeded_call_queue):
        """Test default recipient status is PENDING"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.status == RecipientStatus.PENDING

    def test_recipient_status_values(self):
        """Test all recipient status values exist"""
        expected_statuses = {
            RecipientStatus.PENDING,
            RecipientStatus.CALLING,
            RecipientStatus.RETRYING,
            RecipientStatus.COMPLETED,
            RecipientStatus.FAILED,
            RecipientStatus.NOT_REACHABLE,
            RecipientStatus.SKIPPED,
            RecipientStatus.DLQ,
        }

        assert len(expected_statuses) == 8

    def test_recipient_creation_sets_status(self, seeded_call_queue):
        """Test recipient status can be explicitly set"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            status=RecipientStatus.PENDING
        )

        assert recipient.status == RecipientStatus.PENDING


@pytest.mark.unit
class TestRecipientContactTypeValidation:
    """Test Recipient contact type validation"""

    def test_contact_type_patient(self, seeded_call_queue):
        """Test patient contact type"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="John Doe",
            contact_type="patient",
            language="en"
        )

        assert recipient.contact_type == "patient"

    def test_contact_type_guardian(self, seeded_call_queue):
        """Test guardian contact type"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Parent",
            contact_type="guardian",
            language="en"
        )

        assert recipient.contact_type == "guardian"

    def test_contact_type_caregiver(self, seeded_call_queue):
        """Test caregiver contact type"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Caregiver",
            contact_type="caregiver",
            language="en"
        )

        assert recipient.contact_type == "caregiver"

    def test_contact_type_next_of_kin(self, seeded_call_queue):
        """Test next of kin contact type"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Family",
            contact_type="next_of_kin",
            language="en"
        )

        assert recipient.contact_type == "next_of_kin"


@pytest.mark.unit
class TestRecipientLanguageSupport:
    """Test Recipient language support"""

    def test_recipient_english_language(self, seeded_call_queue):
        """Test English language"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.language == "en"

    def test_recipient_french_language(self, seeded_call_queue):
        """Test French language"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Utilisateur Test",
            contact_type="patient",
            language="fr"
        )

        assert recipient.language == "fr"

    def test_recipient_spanish_language(self, seeded_call_queue):
        """Test Spanish language"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Usuario Prueba",
            contact_type="patient",
            language="es"
        )

        assert recipient.language == "es"

    def test_recipient_haitian_creole_language(self, seeded_call_queue):
        """Test Haitian Creole language"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Itilizatè Tès",
            contact_type="patient",
            language="ht"
        )

        assert recipient.language == "ht"


@pytest.mark.unit
class TestRecipientPriority:
    """Test Recipient priority handling"""

    def test_recipient_default_priority(self, seeded_call_queue):
        """Test default priority is 0"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.priority == 0

    def test_recipient_custom_priority(self, seeded_call_queue):
        """Test custom priority values"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            priority=10
        )

        assert recipient.priority == 10

    def test_recipient_negative_priority(self, seeded_call_queue):
        """Test negative priority (lower priority)"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            priority=-5
        )

        assert recipient.priority == -5


@pytest.mark.unit
class TestRecipientCallTracking:
    """Test Recipient call attempt tracking"""

    def test_recipient_empty_call_timeline(self, seeded_call_queue):
        """Test recipient starts with empty call timeline"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.call_timeline == []

    def test_recipient_with_call_attempts(self, seeded_call_queue):
        """Test recipient with call attempts in timeline"""
        attempt1 = CallAttempt(
            attempt_number=1,
            attempted_at=datetime.utcnow(),
            outcome=CallOutcome.NO_ANSWER,
            failure_reason=FailureReason.NO_ANSWER
        )

        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            call_timeline=[attempt1]
        )

        assert len(recipient.call_timeline) == 1
        assert recipient.call_timeline[0].attempt_number == 1
        assert recipient.call_timeline[0].outcome == CallOutcome.NO_ANSWER

    def test_recipient_retry_count_from_timeline(self, seeded_call_queue):
        """Test counting retries from timeline"""
        attempts = [
            CallAttempt(
                attempt_number=1,
                attempted_at=datetime.utcnow() - timedelta(hours=2),
                outcome=CallOutcome.NO_ANSWER,
                failure_reason=FailureReason.NO_ANSWER
            ),
            CallAttempt(
                attempt_number=2,
                attempted_at=datetime.utcnow() - timedelta(hours=1),
                outcome=CallOutcome.BUSY,
                failure_reason=FailureReason.BUSY
            ),
        ]

        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            call_timeline=attempts
        )

        assert len(recipient.call_timeline) == 2


@pytest.mark.unit
class TestRecipientRetryScheduling:
    """Test Recipient retry scheduling logic"""

    def test_recipient_next_retry_timestamp(self, seeded_call_queue):
        """Test next retry timestamp is set"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            status=RecipientStatus.RETRYING,
            next_retry_at=datetime.utcnow() + timedelta(hours=1)
        )

        assert recipient.next_retry_at is not None
        assert recipient.next_retry_at > datetime.utcnow()

    def test_recipient_retry_count_increments(self, seeded_call_queue):
        """Test retry count increments"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.retry_count == 0

        recipient.retry_count = 1
        assert recipient.retry_count == 1

        recipient.retry_count = 2
        assert recipient.retry_count == 2


@pytest.mark.unit
class TestRecipientDLQTracking:
    """Test Recipient DLQ (Dead Letter Queue) functionality"""

    def test_recipient_not_in_dlq_by_default(self, seeded_call_queue):
        """Test recipient is not in DLQ by default"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.status != RecipientStatus.DLQ

    def test_recipient_dlq_reason(self, seeded_call_queue):
        """Test DLQ reason is stored"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            status=RecipientStatus.DLQ,
            dlq_reason="max_retries_exceeded"
        )

        assert recipient.dlq_reason == "max_retries_exceeded"

    def test_recipient_dlq_timestamp(self, seeded_call_queue):
        """Test DLQ timestamp is tracked"""
        dlq_time = datetime.utcnow()
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            status=RecipientStatus.DLQ,
            dlq_timestamp=dlq_time
        )

        assert recipient.dlq_timestamp == dlq_time


@pytest.mark.unit
class TestRecipientUrgency:
    """Test Recipient urgency tracking"""

    def test_recipient_not_urgent_by_default(self, seeded_call_queue):
        """Test recipient is not marked urgent by default"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.is_urgent is False

    def test_recipient_marked_urgent(self, seeded_call_queue):
        """Test marking recipient as urgent"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            is_urgent=True
        )

        assert recipient.is_urgent is True

    def test_recipient_urgency_reason(self, seeded_call_queue):
        """Test urgency reason is stored"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            is_urgent=True,
            urgency_reason="mentioned_emergency"
        )

        assert recipient.urgency_reason == "mentioned_emergency"


@pytest.mark.unit
class TestRecipientPatientInfo:
    """Test Recipient patient information fields"""

    def test_recipient_patient_name(self, seeded_call_queue):
        """Test patient name field"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Guardian Name",
            patient_name="Patient Name",
            contact_type="guardian",
            language="en"
        )

        assert recipient.patient_name == "Patient Name"

    def test_recipient_patient_relation(self, seeded_call_queue):
        """Test patient relation field"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Parent",
            patient_relation="mother",
            contact_type="guardian",
            language="en"
        )

        assert recipient.patient_relation == "mother"

    def test_recipient_patient_age(self, seeded_call_queue):
        """Test patient age field"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Parent",
            patient_age=5,
            contact_type="guardian",
            language="en"
        )

        assert recipient.patient_age == 5


@pytest.mark.unit
class TestRecipientEventInfo:
    """Test Recipient event information"""

    def test_recipient_with_clarity_event_info(self, seeded_call_queue):
        """Test recipient with Clarity event information"""
        event_info = ClarityEventInfo(
            clarity_verification_id="test-123",
            event_type="Suivi des Enfants",
            event_category="child_vaccination",
            confirmation_message_key="child_vaccination_rr1",
            event_date=datetime.utcnow(),
            facility_name="Test Clinic",
            requires_side_effects=True
        )

        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            event_info=event_info
        )

        assert recipient.event_info is not None
        assert recipient.event_info.clarity_verification_id == "test-123"
        assert recipient.event_info.event_type == "Suivi des Enfants"

    def test_recipient_without_event_info(self, seeded_call_queue):
        """Test recipient without event information"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.event_info is None


@pytest.mark.unit
class TestRecipientCallbackRequest:
    """Test Recipient human callback request tracking"""

    def test_recipient_no_callback_request_by_default(self, seeded_call_queue):
        """Test no callback request by default"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.requested_human_callback is False

    def test_recipient_callback_request_marked(self, seeded_call_queue):
        """Test callback request is marked"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            requested_human_callback=True
        )

        assert recipient.requested_human_callback is True

    def test_recipient_callback_timestamp(self, seeded_call_queue):
        """Test callback request timestamp"""
        now = datetime.utcnow()
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en",
            requested_human_callback=True,
            callback_requested_at=now
        )

        assert recipient.callback_requested_at == now


@pytest.mark.unit
class TestRecipientTimestamps:
    """Test Recipient timestamp tracking"""

    def test_recipient_created_at_set(self, seeded_call_queue):
        """Test created_at timestamp is set"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.created_at is not None

    def test_recipient_updated_at_set(self, seeded_call_queue):
        """Test updated_at timestamp is set"""
        recipient = Recipient(
            queue_id=seeded_call_queue.id,
            contact_phone="+12025551234",
            contact_name="Test User",
            contact_type="patient",
            language="en"
        )

        assert recipient.updated_at is not None
