"""
Models package for Beanie documents.

Exports all model classes for easy imports.
IMPORTANT: Import order matters for Link resolution (parent models before child models)
"""

# Import shared enums first
from backend.app.models.enums import (
    CallType,
    EventCategory,
    ContactType,
    QueueMode,
    QueueState,
    RecipientStatus,
    CallOutcome,
    FailureReason,
    ExternalSource,
    SyncStatus,
    UserRole,
    RETRY_DELAYS_SECONDS,
    NON_RETRIABLE_FAILURES,
    DEFAULT_MAX_RETRIES,
    LANGUAGE_VOICE_MAP,
    SUPPORTED_LANGUAGES,
)

# Import in dependency order: Geography -> CallQueue -> Recipient -> CallRecord
from backend.app.models.user import User
from backend.app.models.geography import Geography, RetentionPolicy, NexusConfig

# CallQueue model
from backend.app.models.call_queue import (
    CallQueue,
    TimeWindow,
    RetryStrategy,
    NexusSyncConfig,
    QueueStats,
    can_transition_to,
)

# Recipient model
from backend.app.models.recipient import (
    Recipient,
    NexusEventInfo,
    CallAttempt,
    ConversationResult,
    determine_contact_type,
)

# CallRecord
from backend.app.models.call_record import (
    CallRecord,
    ConversationData,
    ConversationTurn,
    ConversationStage,
    ConversationState,
    CallTracking,
    RecordingMetadata,
)

# Recording DLQ for failed uploads
from backend.app.models.recording_dlq import (
    RecordingDLQ,
    ErrorEntry,
)

__all__ = [
    # Enums
    "CallType",
    "EventCategory",
    "ContactType",
    "QueueMode",
    "QueueState",
    "RecipientStatus",
    "CallOutcome",
    "FailureReason",
    "ExternalSource",
    "SyncStatus",
    "UserRole",
    # Constants
    "RETRY_DELAYS_SECONDS",
    "NON_RETRIABLE_FAILURES",
    "DEFAULT_MAX_RETRIES",
    "LANGUAGE_VOICE_MAP",
    "SUPPORTED_LANGUAGES",
    # User
    "User",
    # Geography
    "Geography",
    "RetentionPolicy",
    "NexusConfig",
    # CallQueue
    "CallQueue",
    "TimeWindow",
    "RetryStrategy",
    "NexusSyncConfig",
    "QueueStats",
    "can_transition_to",
    # Recipient
    "Recipient",
    "NexusEventInfo",
    "CallAttempt",
    "ConversationResult",
    "determine_contact_type",
    # CallRecord
    "CallRecord",
    "ConversationData",
    "ConversationTurn",
    "ConversationStage",
    "ConversationState",
    "CallTracking",
    "RecordingMetadata",
    # Recording DLQ
    "RecordingDLQ",
    "ErrorEntry",
]
