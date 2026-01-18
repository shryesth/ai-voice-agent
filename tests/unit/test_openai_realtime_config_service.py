"""
Unit tests for OpenAI Realtime API configuration resolution service.

Tests the configuration hierarchy: Campaign > Geography > Global
"""

import pytest
from unittest.mock import patch, MagicMock
from backend.app.services.openai_realtime_config_service import OpenAIRealtimeConfigService
from backend.app.models.campaign import Campaign, CampaignConfig, OpenAIRealtimeCampaignConfig
from backend.app.models.geography import Geography, OpenAIRealtimeGeographyConfig


@pytest.fixture
def mock_campaign_with_prewarmer_enabled():
    """Campaign with prewarmer enabled at campaign level"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=OpenAIRealtimeCampaignConfig(enable_prewarmer=True)
    )
    campaign.geography_id = "test_geography_id"
    return campaign


@pytest.fixture
def mock_campaign_with_prewarmer_disabled():
    """Campaign with prewarmer disabled at campaign level"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=OpenAIRealtimeCampaignConfig(enable_prewarmer=False)
    )
    campaign.geography_id = "test_geography_id"
    return campaign


@pytest.fixture
def mock_campaign_without_config():
    """Campaign without OpenAI Realtime config"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=None
    )
    campaign.geography_id = "test_geography_id"
    return campaign


@pytest.fixture
def mock_geography_with_prewarmer_enabled():
    """Geography with prewarmer enabled"""
    geography = MagicMock(spec=Geography)
    geography.openai_realtime_config = OpenAIRealtimeGeographyConfig(enable_prewarmer=True)
    return geography


@pytest.fixture
def mock_geography_with_prewarmer_disabled():
    """Geography with prewarmer disabled"""
    geography = MagicMock(spec=Geography)
    geography.openai_realtime_config = OpenAIRealtimeGeographyConfig(enable_prewarmer=False)
    return geography


@pytest.fixture
def mock_geography_without_config():
    """Geography without OpenAI Realtime config"""
    geography = MagicMock(spec=Geography)
    geography.openai_realtime_config = None
    return geography


@pytest.mark.unit
@pytest.mark.asyncio
async def test_campaign_override_wins(
    mock_campaign_with_prewarmer_enabled,
    mock_geography_with_prewarmer_disabled
):
    """Campaign Realtime config overrides geography and global"""
    # Global = False (via mock), Geography = False, Campaign = True
    with patch("backend.app.services.openai_realtime_config_service.settings") as mock_settings:
        mock_settings.openai_realtime_prewarmer_enabled = False

        result = await OpenAIRealtimeConfigService.is_prewarmer_enabled(
            mock_campaign_with_prewarmer_enabled,
            mock_geography_with_prewarmer_disabled
        )

        assert result is True, "Campaign override should win over geography and global"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_geography_override_wins(
    mock_campaign_without_config,
    mock_geography_with_prewarmer_enabled
):
    """Geography Realtime config overrides global when campaign has None"""
    # Global = False (via mock), Geography = True, Campaign = None
    with patch("backend.app.services.openai_realtime_config_service.settings") as mock_settings:
        mock_settings.openai_realtime_prewarmer_enabled = False

        result = await OpenAIRealtimeConfigService.is_prewarmer_enabled(
            mock_campaign_without_config,
            mock_geography_with_prewarmer_enabled
        )

        assert result is True, "Geography override should win over global"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_global_default_used(
    mock_campaign_without_config,
    mock_geography_without_config
):
    """Global Realtime config used when geography and campaign have None"""
    # Global = True (via mock), Geography = None, Campaign = None
    with patch("backend.app.services.openai_realtime_config_service.settings") as mock_settings:
        mock_settings.openai_realtime_prewarmer_enabled = True

        result = await OpenAIRealtimeConfigService.is_prewarmer_enabled(
            mock_campaign_without_config,
            mock_geography_without_config
        )

        assert result is True, "Global default should be used when others are None"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_campaign_disabled_overrides_geography_enabled(
    mock_campaign_with_prewarmer_disabled,
    mock_geography_with_prewarmer_enabled
):
    """Campaign disabled overrides geography enabled"""
    # Campaign = False, Geography = True
    result = await OpenAIRealtimeConfigService.is_prewarmer_enabled(
        mock_campaign_with_prewarmer_disabled,
        mock_geography_with_prewarmer_enabled
    )

    assert result is False, "Campaign disabled should override geography enabled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetches_geography_if_not_provided():
    """Service fetches geography if not provided"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=None
    )
    campaign.geography_id = "test_geography_id"

    mock_geography = MagicMock(spec=Geography)
    mock_geography.openai_realtime_config = OpenAIRealtimeGeographyConfig(enable_prewarmer=True)

    with patch("backend.app.services.openai_realtime_config_service.Geography") as mock_geo_class:
        mock_geo_class.get = MagicMock(return_value=mock_geography)

        with patch("backend.app.services.openai_realtime_config_service.settings") as mock_settings:
            mock_settings.openai_realtime_prewarmer_enabled = False

            result = await OpenAIRealtimeConfigService.is_prewarmer_enabled(campaign, None)

            assert result is True
            mock_geo_class.get.assert_called_once()


@pytest.mark.unit
def test_get_voice_campaign_override():
    """Get voice with campaign override"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=OpenAIRealtimeCampaignConfig(voice="nova")
    )

    voice = OpenAIRealtimeConfigService.get_voice(campaign, "en")

    assert voice == "nova", "Campaign voice override should be used"


@pytest.mark.unit
def test_get_voice_language_default():
    """Get voice using language default mapping"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=None
    )

    # Test each language mapping
    assert OpenAIRealtimeConfigService.get_voice(campaign, "en") == "alloy"
    assert OpenAIRealtimeConfigService.get_voice(campaign, "es") == "nova"
    assert OpenAIRealtimeConfigService.get_voice(campaign, "fr") == "alloy"
    assert OpenAIRealtimeConfigService.get_voice(campaign, "ht") == "echo"
    assert OpenAIRealtimeConfigService.get_voice(campaign, "unknown") == "alloy"  # Default fallback


@pytest.mark.unit
def test_get_temperature_campaign_override():
    """Get temperature with campaign override"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=OpenAIRealtimeCampaignConfig(temperature=0.5)
    )

    temperature = OpenAIRealtimeConfigService.get_temperature(campaign)

    assert temperature == 0.5, "Campaign temperature override should be used"


@pytest.mark.unit
def test_get_temperature_default():
    """Get temperature using default value"""
    campaign = MagicMock(spec=Campaign)
    campaign.config = CampaignConfig(
        patient_list=["+12025551234"],
        openai_realtime_config=None
    )

    temperature = OpenAIRealtimeConfigService.get_temperature(campaign)

    assert temperature == 0.8, "Default temperature should be 0.8"
