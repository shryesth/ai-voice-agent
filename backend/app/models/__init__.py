"""
Models package for Beanie documents.

Exports all model classes for easy imports.
IMPORTANT: Import order matters for Link resolution (parent models before child models)
"""

# Import in dependency order: Geography -> Campaign -> CallRecord
from backend.app.models.user import User, UserRole
from backend.app.models.geography import Geography, RetentionPolicy
from backend.app.models.campaign import Campaign, CampaignState, CampaignConfig, CampaignStats, TimeWindow, DayOfWeek
from backend.app.models.call_record import (
    CallRecord,
    CallOutcome,
    FeedbackData,
    ConversationTurn,
    ConversationStage,
    ConversationState,
    CallTracking,
)
from backend.app.models.queue_entry import QueueEntry, QueueState, FailureReason, RetryHistory

__all__ = [
    "User",
    "UserRole",
    "Geography",
    "RetentionPolicy",
    "Campaign",
    "CampaignState",
    "CampaignConfig",
    "CampaignStats",
    "TimeWindow",
    "DayOfWeek",
    "CallRecord",
    "CallOutcome",
    "FeedbackData",
    "ConversationTurn",
    "ConversationStage",
    "ConversationState",
    "CallTracking",
    "QueueEntry",
    "QueueState",
    "FailureReason",
    "RetryHistory",
]
