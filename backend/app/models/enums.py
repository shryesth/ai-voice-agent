"""
Shared enums for the Supervisor AI Calling Agent platform.

This module contains all enum types used across the application.
"""

from enum import Enum


class CallType(str, Enum):
    """Types of outbound calls (features)."""

    PATIENT_FEEDBACK = "patient_feedback"  # Patient feedback collection (default, all geos)
    APPOINTMENT_REMINDER = "appointment_reminder"  # Future
    SURVEY = "survey"  # Future
    CUSTOM = "custom"  # Future


class EventCategory(str, Enum):
    """
    Categories of health events (for Patient Feedback Collection).

    All use same flow: greet → confirm identity → confirm visit → confirm service → [rating]
    The event_type determines the confirmation message.
    """

    CHILD_VACCINATION = "child_vaccination"  # Vaccination events (may check side effects)
    CHILD_HEALTH = "child_health"  # Deworming, Vitamin A, malnutrition screening
    PRENATAL = "prenatal"  # Antenatal care visits
    MATERNITY = "maternity"  # Deliveries, C-sections
    POSTNATAL = "postnatal"  # Postnatal visits
    CURATIVE = "curative"  # Morbidity, new consultations
    REFERRAL = "referral"  # Institutional referrals
    FAMILY_PLANNING = "family_planning"  # Family planning services
    TB = "tb"  # Tuberculosis (NO_CALL - data only)
    HIV = "hiv"  # HIV/ARV (NO_CALL - data only)
    OTHER = "other"  # Default category


class ContactType(str, Enum):
    """Who we're calling."""

    PATIENT = "patient"  # Calling patient directly
    GUARDIAN = "guardian"  # Calling parent/guardian (for children)
    CAREGIVER = "caregiver"  # Calling caregiver
    NEXT_OF_KIN = "next_of_kin"  # Calling family member
    UNKNOWN = "unknown"  # Not specified


class QueueMode(str, Enum):
    """How the queue operates."""

    FOREVER = "forever"  # Continuously pulls from external source
    BATCH = "batch"  # One-time batch, completes when done
    MANUAL = "manual"  # Manual entry only


class QueueState(str, Enum):
    """Queue lifecycle state."""

    DRAFT = "draft"  # Not yet started
    ACTIVE = "active"  # Processing calls
    PAUSED = "paused"  # Temporarily paused
    COMPLETED = "completed"  # All calls done (batch mode)
    CANCELLED = "cancelled"  # Stopped permanently


class RecipientStatus(str, Enum):
    """Recipient processing status."""

    PENDING = "pending"  # Awaiting first attempt
    CALLING = "calling"  # Call in progress
    RETRYING = "retrying"  # Scheduled for retry
    # Post-call states
    READY_TO_SYNC = "ready_to_sync"  # Call complete, recording saved, ready for Clarity sync
    # Terminal states (after Clarity sync or final disposition)
    COMPLETED = "completed"  # Call successful, synced to Clarity (-> Clarity VALID)
    FAILED = "failed"  # Call failed, not verified (-> Clarity NOT_VALID)
    NOT_REACHABLE = "not_reachable"  # Max retries exhausted (-> Clarity NOT_REACHABLE)
    SKIPPED = "skipped"  # Manually skipped
    DLQ = "dlq"  # Dead letter queue


class CallOutcome(str, Enum):
    """Detailed call outcome for timeline."""

    # Successful
    COMPLETED_FULL = "completed_full"
    COMPLETED_PARTIAL = "completed_partial"

    # Needs follow-up
    WRONG_PERSON = "wrong_person"
    VOICEMAIL = "voicemail"
    REQUEST_HUMAN_CALLBACK = "request_human_callback"
    NEEDS_VERIFICATION = "needs_verification"

    # Connection issues
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    INVALID_NUMBER = "invalid_number"
    REJECTED = "rejected"
    NETWORK_FAILURE = "network_failure"
    TIMEOUT = "timeout"

    # Technical
    TECHNICAL_ERROR = "technical_error"
    SHORT_DURATION = "short_duration"  # <30 seconds


class FailureReason(str, Enum):
    """Why a call failed (for retry logic)."""

    NO_ANSWER = "no_answer"  # 30 min retry
    BUSY = "busy"  # 1 hour retry
    FAILED = "failed"  # 15 min retry
    TIMEOUT = "timeout"  # 30 min retry
    PERSON_NOT_AVAILABLE = "person_not_available"  # 2 hour retry
    SHORT_DURATION = "short_duration"  # 1 hour retry
    VOICEMAIL = "voicemail"  # 2 hour retry
    WRONG_PERSON = "wrong_person"  # 2 hour retry
    NEEDS_VERIFICATION = "needs_verification"  # 2 hour retry
    # Terminal (no retry)
    INVALID_NUMBER = "invalid_number"
    REJECTED = "rejected"
    REQUEST_HUMAN_CALLBACK = "request_human_callback"


class ExternalSource(str, Enum):
    """Where recipients come from."""

    CLARITY = "clarity"
    MANUAL = "manual"
    CSV_IMPORT = "csv_import"


class SyncStatus(str, Enum):
    """Clarity sync status for recipients."""

    PENDING = "pending"  # Not yet synced
    SYNCED = "synced"  # Successfully synced
    FAILED = "failed"  # Sync failed


class DisconnectSource(str, Enum):
    """Source of call disconnection."""

    USER_HANGUP = "user_hangup"  # User hung up
    AGENT_HANGUP = "agent_hangup"  # Agent ended call
    TWILIO_BUSY = "twilio_busy"  # Twilio reported busy
    TWILIO_NO_ANSWER = "twilio_no_answer"  # Twilio reported no answer
    TWILIO_FAILED = "twilio_failed"  # Twilio reported failed
    TIMEOUT = "timeout"  # Call timeout
    ERROR = "error"  # Technical error


class UserRole(str, Enum):
    """User roles for RBAC."""

    ADMIN = "admin"
    USER = "user"


# Retry configuration constants
RETRY_DELAYS_SECONDS = {
    FailureReason.NO_ANSWER: 1800,  # 30 min
    FailureReason.BUSY: 3600,  # 1 hour
    FailureReason.FAILED: 900,  # 15 min
    FailureReason.TIMEOUT: 1800,  # 30 min
    FailureReason.PERSON_NOT_AVAILABLE: 7200,  # 2 hours
    FailureReason.SHORT_DURATION: 3600,  # 1 hour
    FailureReason.VOICEMAIL: 7200,  # 2 hours
    FailureReason.WRONG_PERSON: 7200,  # 2 hours
    FailureReason.NEEDS_VERIFICATION: 7200,  # 2 hours
}

# Non-retriable failure reasons (terminal states)
NON_RETRIABLE_FAILURES = {
    FailureReason.INVALID_NUMBER,
    FailureReason.REJECTED,
    FailureReason.REQUEST_HUMAN_CALLBACK,
}

# Default max retries
DEFAULT_MAX_RETRIES = 3

# Language to voice mapping for OpenAI Realtime
LANGUAGE_VOICE_MAP = {
    "en": "alloy",
    "es": "nova",
    "fr": "alloy",
    "ht": "echo",
}

# Supported languages
SUPPORTED_LANGUAGES = ["en", "ht", "fr", "es"]
