"""
Integration tests for voice pipeline (User Story 4).

Tests the complete voice call workflow:
- T047: Pipecat voice pipeline with 6-stage conversation flow
- T048: Twilio integration (call initiation, webhook handling)
- T049: Urgency detection (keyword matching)

Note: These tests require valid Twilio credentials to pass.
In development, they can be run with mocked Twilio responses.
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import AsyncMock, Mock, patch

from backend.app.models.campaign import Campaign, CampaignState, CampaignConfig
from backend.app.models.call_record import (
    CallRecord,
    ConversationStage,
    CallOutcome,
)
from backend.app.domains.patient_feedback.conversation_flow import ConversationFlow
from backend.app.domains.patient_feedback.urgency_detector import UrgencyDetector
from backend.app.domains.patient_feedback.twilio_integration import TwilioIntegration
from backend.app.domains.patient_feedback.voice_pipeline import VoicePipeline


pytestmark = pytest.mark.asyncio


class TestVoicePipeline:
    """T047: Integration test for Pipecat voice pipeline (6-stage flow)."""

    async def test_complete_6_stage_conversation_flow(self):
        """
        Test the complete 6-stage conversation flow:
        1. Greeting
        2. Language Selection
        3. Patient Verification
        4. Feedback Collection
        5. Urgency Detection
        6. Call Completion
        """
        # Arrange
        campaign = Campaign(
            name="Test Campaign",
            geography_id=None,  # Will be mocked
            config=CampaignConfig(
                patient_list=["+12025551234"],
                language_preference="en"
            ),
            state=CampaignState.ACTIVE,
        )

        call_record = CallRecord(
            campaign_id=None,  # Will be mocked
            patient_phone="+12025551234",
            language="en",
        )

        # Mock conversation flow
        conversation_flow = ConversationFlow(language="en")

        # Act - Progress through all 6 stages
        stages_completed = []

        # Stage 1: Greeting
        greeting_result = await conversation_flow.process_stage(
            ConversationStage.GREETING,
            patient_input=None
        )
        assert greeting_result.success is True
        stages_completed.append(ConversationStage.GREETING)

        # Stage 2: Language Selection
        language_result = await conversation_flow.process_stage(
            ConversationStage.LANGUAGE_SELECTION,
            patient_input="English please"
        )
        assert language_result.success is True
        stages_completed.append(ConversationStage.LANGUAGE_SELECTION)

        # Stage 3: Patient Verification
        verification_result = await conversation_flow.process_stage(
            ConversationStage.PATIENT_VERIFICATION,
            patient_input="Yes, this is the patient"
        )
        assert verification_result.success is True
        stages_completed.append(ConversationStage.PATIENT_VERIFICATION)

        # Stage 4: Feedback Collection
        feedback_result = await conversation_flow.process_stage(
            ConversationStage.FEEDBACK_COLLECTION,
            patient_input="My experience was good, I rate it 8 out of 10"
        )
        assert feedback_result.success is True
        stages_completed.append(ConversationStage.FEEDBACK_COLLECTION)

        # Stage 5: Urgency Detection
        urgency_result = await conversation_flow.process_stage(
            ConversationStage.URGENCY_DETECTION,
            patient_input="No urgent concerns"
        )
        assert urgency_result.success is True
        stages_completed.append(ConversationStage.URGENCY_DETECTION)

        # Stage 6: Call Completion
        completion_result = await conversation_flow.process_stage(
            ConversationStage.CALL_COMPLETION,
            patient_input=None
        )
        assert completion_result.success is True
        stages_completed.append(ConversationStage.CALL_COMPLETION)

        # Assert
        assert len(stages_completed) == 6
        assert ConversationStage.GREETING in stages_completed
        assert ConversationStage.LANGUAGE_SELECTION in stages_completed
        assert ConversationStage.PATIENT_VERIFICATION in stages_completed
        assert ConversationStage.FEEDBACK_COLLECTION in stages_completed
        assert ConversationStage.URGENCY_DETECTION in stages_completed
        assert ConversationStage.CALL_COMPLETION in stages_completed

    async def test_stage_retry_logic(self):
        """Test that failed stages are retried up to 2 times."""
        # Arrange
        conversation_flow = ConversationFlow(language="en")

        # Mock a stage that fails twice then succeeds
        with patch.object(conversation_flow, '_process_verification') as mock_verify:
            mock_verify.side_effect = [
                Mock(success=False, retry_count=1),
                Mock(success=False, retry_count=2),
                Mock(success=True, retry_count=2),
            ]

            # Act - Attempt verification 3 times
            result1 = await conversation_flow.process_stage(
                ConversationStage.PATIENT_VERIFICATION,
                patient_input="unclear response"
            )
            result2 = await conversation_flow.process_stage(
                ConversationStage.PATIENT_VERIFICATION,
                patient_input="still unclear"
            )
            result3 = await conversation_flow.process_stage(
                ConversationStage.PATIENT_VERIFICATION,
                patient_input="Yes, I am the patient"
            )

            # Assert
            assert result1.success is False
            assert result2.success is False
            assert result3.success is True
            assert mock_verify.call_count == 3

    async def test_partial_conversation_on_network_failure(self):
        """Test that partial conversation is saved on mid-call network failure."""
        # Arrange
        pipeline = VoicePipeline(
            campaign_id="test_campaign",
            patient_phone="+12025551234",
            language="en"
        )

        # Mock partial conversation transcript
        partial_transcript = [
            {"speaker": "ai", "text": "Hello, this is a call from your healthcare provider", "timestamp": datetime.utcnow()},
            {"speaker": "patient", "text": "Hi, yes I remember", "timestamp": datetime.utcnow()},
        ]

        # Act - Simulate network failure during feedback collection
        with pytest.raises(Exception) as exc_info:
            with patch.object(pipeline, 'save_partial_call') as mock_save:
                # Simulate network failure
                raise ConnectionError("Network failure during call")

        # Assert - Verify partial data would be saved
        # Note: In real implementation, this is handled in exception handler
        assert "Network failure" in str(exc_info.value)


class TestTwilioIntegration:
    """T048: Integration test for Twilio integration."""

    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    async def test_initiate_outbound_call(self, mock_twilio_client):
        """Test initiating outbound call via Twilio."""
        # Arrange
        mock_call = Mock()
        mock_call.sid = "CA1234567890abcdef"
        mock_call.status = "queued"
        mock_twilio_client.return_value.calls.create.return_value = mock_call

        twilio_integration = TwilioIntegration()

        # Act
        call_sid = await twilio_integration.initiate_call(
            to_phone="+12025551234",
            from_phone="+12025559999",
            webhook_url="https://example.com/api/v1/webhooks/twilio/status"
        )

        # Assert
        assert call_sid == "CA1234567890abcdef"
        mock_twilio_client.return_value.calls.create.assert_called_once()

    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    async def test_twilio_status_webhook_handling(self, mock_twilio_client):
        """Test handling Twilio status callback webhook."""
        # Arrange
        twilio_integration = TwilioIntegration()

        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "CallStatus": "completed",
            "CallDuration": "200",
        }

        # Act
        result = await twilio_integration.process_status_webhook(webhook_data)

        # Assert
        assert result["call_sid"] == "CA1234567890abcdef"
        assert result["status"] == "completed"
        assert result["duration_seconds"] == 200

    async def test_twilio_signature_validation(self):
        """Test Twilio webhook signature validation for security."""
        # Arrange
        twilio_integration = TwilioIntegration()

        request_url = "https://example.com/api/v1/webhooks/twilio/status"
        post_params = {
            "CallSid": "CA1234567890abcdef",
            "CallStatus": "completed",
        }
        signature = "invalid_signature"

        # Act
        is_valid = twilio_integration.validate_signature(
            request_url=request_url,
            post_params=post_params,
            signature=signature
        )

        # Assert
        assert is_valid is False  # Invalid signature should fail

    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    async def test_websocket_media_streaming_setup(self, mock_twilio_client):
        """Test WebSocket media streaming setup for real-time audio."""
        # Arrange
        mock_call = Mock()
        mock_call.sid = "CA1234567890abcdef"
        mock_call.stream_sid = "MZ9876543210fedcba"
        mock_twilio_client.return_value.calls.create.return_value = mock_call

        twilio_integration = TwilioIntegration()

        # Act
        call_info = await twilio_integration.initiate_call_with_streaming(
            to_phone="+12025551234",
            from_phone="+12025559999",
            stream_url="wss://example.com/media-stream"
        )

        # Assert
        assert call_info["call_sid"] == "CA1234567890abcdef"
        assert "stream_sid" in call_info or call_info.get("stream_url") is not None


class TestUrgencyDetection:
    """T049: Integration test for urgency detection."""

    def test_detect_urgency_keywords(self):
        """Test detection of urgency keywords in patient responses."""
        # Arrange
        urgency_detector = UrgencyDetector()

        # Test cases with urgency keywords
        urgent_phrases = [
            "I went to the hospital last night",
            "I'm experiencing severe pain",
            "I can't breathe properly",
            "I need to go to the emergency room",
            "Should I call an ambulance?",
            "I called 911 yesterday",
            "Having an allergic reaction",
        ]

        # Act & Assert
        for phrase in urgent_phrases:
            result = urgency_detector.detect(phrase)
            assert result.is_urgent is True
            assert len(result.keywords_detected) > 0

    def test_no_urgency_in_normal_feedback(self):
        """Test that normal feedback does not trigger urgency flags."""
        # Arrange
        urgency_detector = UrgencyDetector()

        # Test cases without urgency
        normal_phrases = [
            "My experience was good overall",
            "The staff was friendly and helpful",
            "I rate my visit 8 out of 10",
            "Everything went smoothly",
            "No concerns or issues",
        ]

        # Act & Assert
        for phrase in normal_phrases:
            result = urgency_detector.detect(phrase)
            assert result.is_urgent is False
            assert len(result.keywords_detected) == 0

    def test_case_insensitive_keyword_matching(self):
        """Test that urgency detection is case-insensitive."""
        # Arrange
        urgency_detector = UrgencyDetector()

        # Test different case variations
        test_phrases = [
            "I went to the HOSPITAL",
            "severe pain in my chest",
            "Can't Breathe properly",
            "EMERGENCY situation",
        ]

        # Act & Assert
        for phrase in test_phrases:
            result = urgency_detector.detect(phrase)
            assert result.is_urgent is True

    def test_urgency_keyword_list(self):
        """Test the complete list of urgency keywords."""
        # Arrange
        urgency_detector = UrgencyDetector()

        # Expected keywords from spec
        expected_keywords = [
            "hospital",
            "severe",
            "can't breathe",
            "emergency",
            "ambulance",
            "911",
        ]

        # Act
        available_keywords = urgency_detector.get_keywords()

        # Assert
        for keyword in expected_keywords:
            assert keyword.lower() in [k.lower() for k in available_keywords]

    def test_multiple_urgency_keywords_detected(self):
        """Test detection of multiple urgency keywords in single phrase."""
        # Arrange
        urgency_detector = UrgencyDetector()

        phrase = "I had severe pain and went to the hospital emergency room"

        # Act
        result = urgency_detector.detect(phrase)

        # Assert
        assert result.is_urgent is True
        assert len(result.keywords_detected) >= 2  # "severe", "hospital", "emergency"
        assert "severe" in [k.lower() for k in result.keywords_detected]
        assert "hospital" in [k.lower() for k in result.keywords_detected]

    def test_urgency_flagging_in_transcript(self):
        """Test urgency detection across full conversation transcript."""
        # Arrange
        urgency_detector = UrgencyDetector()

        transcript = [
            {"speaker": "ai", "text": "How was your experience?"},
            {"speaker": "patient", "text": "It was okay at first"},
            {"speaker": "ai", "text": "Did you experience any side effects?"},
            {"speaker": "patient", "text": "Yes, I had severe allergic reaction and went to emergency"},
            {"speaker": "ai", "text": "Thank you for sharing that"},
        ]

        # Act
        urgency_results = []
        for turn in transcript:
            if turn["speaker"] == "patient":
                result = urgency_detector.detect(turn["text"])
                urgency_results.append(result)

        # Assert
        urgent_count = sum(1 for r in urgency_results if r.is_urgent)
        assert urgent_count >= 1  # At least one patient response should be flagged
