"""
Models package for Beanie documents.

Exports all model classes for easy imports.
"""

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
]
