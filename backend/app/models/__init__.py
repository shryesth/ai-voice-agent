"""
Models package for Beanie documents.

Exports all model classes for easy imports.
IMPORTANT: Import order matters for Link resolution (parent models before child models)

NEW Supervisor models:
- CallQueue (replaces Campaign)
- Recipient (replaces QueueEntry)
- Updated Geography with ClarityConfig
- Updated CallRecord with new fields

Legacy models (Campaign, QueueEntry) are kept for backward compatibility but deprecated.
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

# Import in dependency order: Geography -> CallQueue/Campaign -> Recipient/QueueEntry -> CallRecord
from backend.app.models.user import User
from backend.app.models.geography import Geography, RetentionPolicy, ClarityConfig

# NEW: CallQueue model (replaces Campaign)
from backend.app.models.call_queue import (
    CallQueue,
    TimeWindow,
    RetryStrategy,
    ClaritySyncConfig,
    QueueStats,
    can_transition_to,
)

# NEW: Recipient model (replaces QueueEntry)
from backend.app.models.recipient import (
    Recipient,
    ClarityEventInfo,
    CallAttempt,
    ConversationResult,
    determine_contact_type,
)

# LEGACY: Campaign model (deprecated, use CallQueue)
from backend.app.models.campaign import (
    Campaign,
    CampaignState,
    CampaignConfig,
    CampaignStats as LegacyCampaignStats,
    TimeWindow as LegacyTimeWindow,
    DayOfWeek,
)

# LEGACY: QueueEntry model (deprecated, use Recipient)
from backend.app.models.queue_entry import (
    QueueEntry,
    QueueState as LegacyQueueState,
    FailureReason as LegacyFailureReason,
    RetryHistory,
)

# CallRecord with new fields
from backend.app.models.call_record import (
    CallRecord,
    ConversationData,
    FeedbackData,  # Alias for ConversationData
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
    "ClarityConfig",
    # NEW: CallQueue
    "CallQueue",
    "TimeWindow",
    "RetryStrategy",
    "ClaritySyncConfig",
    "QueueStats",
    "can_transition_to",
    # NEW: Recipient
    "Recipient",
    "ClarityEventInfo",
    "CallAttempt",
    "ConversationResult",
    "determine_contact_type",
    # CallRecord
    "CallRecord",
    "ConversationData",
    "FeedbackData",
    "ConversationTurn",
    "ConversationStage",
    "ConversationState",
    "CallTracking",
    "RecordingMetadata",
    # LEGACY (deprecated)
    "Campaign",
    "CampaignState",
    "CampaignConfig",
    "LegacyCampaignStats",
    "LegacyTimeWindow",
    "DayOfWeek",
    "QueueEntry",
    "LegacyQueueState",
    "LegacyFailureReason",
    "RetryHistory",
    # Recording DLQ
    "RecordingDLQ",
    "ErrorEntry",
]
