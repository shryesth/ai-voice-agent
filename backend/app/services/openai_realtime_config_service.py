"""
OpenAI Realtime API configuration resolution service.

Resolves Realtime API configuration from Campaign → Geography → Global with proper precedence.
"""

from typing import Optional
from backend.app.models.campaign import Campaign
from backend.app.models.geography import Geography
from backend.app.core.config import settings


class OpenAIRealtimeConfigService:
    """Resolves OpenAI Realtime API configuration from hierarchy"""

    @staticmethod
    async def is_prewarmer_enabled(
        campaign: Campaign,
        geography: Optional[Geography] = None
    ) -> bool:
        """
        Determine if Realtime API prewarmer is enabled for this call.

        Precedence: Campaign > Geography > Global

        Args:
            campaign: Campaign model
            geography: Geography model (optional, will fetch if needed)

        Returns:
            True if Realtime API prewarmer should be used
        """
        # Campaign level override
        if campaign.config and campaign.config.openai_realtime_config:
            if campaign.config.openai_realtime_config.enable_prewarmer is not None:
                return campaign.config.openai_realtime_config.enable_prewarmer

        # Geography level override
        if geography is None and campaign.geography_id:
            geography = await Geography.get(campaign.geography_id)

        if geography and geography.openai_realtime_config:
            if geography.openai_realtime_config.enable_prewarmer is not None:
                return geography.openai_realtime_config.enable_prewarmer

        # Global default
        return settings.openai_realtime_prewarmer_enabled

    @staticmethod
    def get_voice(campaign: Campaign, language: str) -> str:
        """Get OpenAI Realtime voice for campaign, considering overrides and language"""
        # Campaign override
        if campaign.config and campaign.config.openai_realtime_config:
            if campaign.config.openai_realtime_config.voice:
                return campaign.config.openai_realtime_config.voice

        # Language default mapping
        language_voice_map = {
            "en": "alloy",
            "es": "nova",
            "fr": "alloy",
            "ht": "echo"
        }
        return language_voice_map.get(language, "alloy")

    @staticmethod
    def get_temperature(campaign: Campaign) -> float:
        """Get OpenAI Realtime API temperature for campaign"""
        # Campaign override
        if campaign.config and campaign.config.openai_realtime_config:
            if campaign.config.openai_realtime_config.temperature is not None:
                return campaign.config.openai_realtime_config.temperature

        # Default
        return 0.8
