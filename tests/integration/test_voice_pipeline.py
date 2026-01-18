"""
Integration tests for voice pipeline (User Story 4).

Tests the complete voice call workflow:
- T047: FlowManager-based 6-stage conversation flow
- T048: Twilio integration (call initiation, webhook handling)
- T049: Urgency detection (keyword matching)

Note: These tests require valid Twilio credentials to pass.
In development, they can be run with mocked Twilio responses.
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from backend.app.domains.patient_feedback.flow_manager import (
    FlowManager, NodeConfig, FlowArgs, FlowResult, FlowsFunctionSchema
)
from backend.app.domains.patient_feedback.conversation_flow import (
    create_greeting_node,
    create_language_selection_node,
    create_verification_node,
    create_feedback_node,
    create_urgency_detection_node,
    create_completion_node,
    GreetingResult,
    LanguageResult,
    VerificationResult,
    FeedbackResult,
    UrgencyResult,
    CompletionResult,
)
from backend.app.domains.patient_feedback.urgency_detector import UrgencyDetector
from backend.app.domains.patient_feedback.twilio_integration import TwilioIntegration


pytestmark = pytest.mark.asyncio


class TestFlowManager:
    """T047: Integration test for FlowManager-based 6-stage conversation flow."""

    async def test_flow_manager_initialization(self):
        """Test FlowManager initializes with correct starting node."""
        # Arrange
        greeting_node = create_greeting_node()

        # Act
        flow_manager = FlowManager(initial_node=greeting_node)
        await flow_manager.initialize()

        # Assert
        assert flow_manager.current_stage == "greeting"
        assert flow_manager._initialized is True
        assert flow_manager.is_complete is False

    async def test_greeting_stage_success(self):
        """Test greeting stage transitions to language selection."""
        # Arrange
        greeting_node = create_greeting_node()
        flow_manager = FlowManager(initial_node=greeting_node)
        await flow_manager.initialize()

        # Act - Simulate patient acknowledging greeting
        result, next_node = await flow_manager.handle_function_call(
            "acknowledge_greeting",
            {"acknowledged": True}
        )

        # Assert
        assert isinstance(result, GreetingResult)
        assert result.acknowledged is True
        assert flow_manager.state.get("greeted") is True
        assert flow_manager.current_stage == "language_selection"

    async def test_language_selection_stage(self):
        """Test language selection transitions to verification."""
        # Arrange - Start at language selection
        language_node = create_language_selection_node()
        flow_manager = FlowManager(initial_node=language_node)
        await flow_manager.initialize()

        # Act - Simulate patient selecting Spanish
        result, next_node = await flow_manager.handle_function_call(
            "select_language",
            {"language": "es"}
        )

        # Assert
        assert isinstance(result, LanguageResult)
        assert result.language == "es"
        assert flow_manager.state.get("language") == "es"
        assert flow_manager.current_stage == "patient_verification"

    async def test_verification_stage_success(self):
        """Test verification with authorized person transitions to feedback."""
        # Arrange
        verification_node = create_verification_node()
        flow_manager = FlowManager(initial_node=verification_node)
        await flow_manager.initialize()

        # Act - Simulate patient confirming identity
        result, next_node = await flow_manager.handle_function_call(
            "verify_patient_identity",
            {"is_appropriate_person": True}
        )

        # Assert
        assert isinstance(result, VerificationResult)
        assert result.verified is True
        assert result.is_patient is True
        assert flow_manager.state.get("verified") is True
        assert flow_manager.current_stage == "feedback_collection"

    async def test_verification_stage_wrong_person(self):
        """Test verification with wrong person ends call gracefully."""
        # Arrange
        verification_node = create_verification_node()
        flow_manager = FlowManager(initial_node=verification_node)
        await flow_manager.initialize()

        # Act - Simulate wrong person on call
        result, next_node = await flow_manager.handle_function_call(
            "verify_patient_identity",
            {"is_appropriate_person": False}
        )

        # Assert
        assert isinstance(result, VerificationResult)
        assert result.verified is False
        assert flow_manager.state.get("wrong_person") is True
        assert flow_manager.current_stage == "call_completion"

    async def test_feedback_collection_stage(self):
        """Test feedback collection stores data and transitions to urgency."""
        # Arrange
        feedback_node = create_feedback_node()
        flow_manager = FlowManager(initial_node=feedback_node)
        await flow_manager.initialize()

        # Act - Simulate patient providing feedback
        result, next_node = await flow_manager.handle_function_call(
            "record_feedback",
            {
                "satisfaction_rating": 8,
                "specific_concerns": "Wait times were long",
                "side_effects": "Mild headache",
                "experience_quality": "Staff was very friendly"
            }
        )

        # Assert
        assert isinstance(result, FeedbackResult)
        assert result.satisfaction_rating == 8
        assert result.specific_concerns == "Wait times were long"
        assert "feedback" in flow_manager.state
        assert flow_manager.state["feedback"]["satisfaction"] == 8
        assert flow_manager.current_stage == "urgency_detection"

    async def test_urgency_detection_with_keywords(self):
        """Test urgency detection flags urgent keywords."""
        # Arrange
        urgency_node = create_urgency_detection_node()
        flow_manager = FlowManager(initial_node=urgency_node)
        await flow_manager.initialize()

        # Act - Simulate urgent keywords detected
        result, next_node = await flow_manager.handle_function_call(
            "detect_urgency",
            {"urgent_keywords": ["hospital", "severe"]}
        )

        # Assert
        assert isinstance(result, UrgencyResult)
        assert result.flagged is True
        assert "hospital" in result.keywords
        assert flow_manager.state.get("urgency_flagged") is True
        assert flow_manager.current_stage == "call_completion"

    async def test_urgency_detection_no_keywords(self):
        """Test urgency detection with no urgent keywords."""
        # Arrange
        urgency_node = create_urgency_detection_node()
        flow_manager = FlowManager(initial_node=urgency_node)
        await flow_manager.initialize()

        # Act - No urgent keywords
        result, next_node = await flow_manager.handle_function_call(
            "detect_urgency",
            {"urgent_keywords": []}
        )

        # Assert
        assert isinstance(result, UrgencyResult)
        assert result.flagged is False
        assert flow_manager.state.get("urgency_flagged") is None
        assert flow_manager.current_stage == "call_completion"

    async def test_call_completion_ends_flow(self):
        """Test call completion marks flow as complete."""
        # Arrange
        completion_node = create_completion_node("success")
        flow_manager = FlowManager(initial_node=completion_node)
        await flow_manager.initialize()

        # Act - End the call
        result, next_node = await flow_manager.handle_function_call(
            "end_call",
            {"acknowledged": True}
        )

        # Assert
        assert isinstance(result, CompletionResult)
        assert result.reason == "success"
        assert flow_manager.state.get("completed") is True
        assert flow_manager.is_complete is True

    async def test_complete_6_stage_flow(self):
        """Test complete progression through all 6 stages."""
        # Arrange
        flow_manager = FlowManager(initial_node=create_greeting_node())
        await flow_manager.initialize()
        stages_visited = [flow_manager.current_stage]

        # Stage 1: Greeting
        await flow_manager.handle_function_call("acknowledge_greeting", {"acknowledged": True})
        stages_visited.append(flow_manager.current_stage)

        # Stage 2: Language Selection
        await flow_manager.handle_function_call("select_language", {"language": "en"})
        stages_visited.append(flow_manager.current_stage)

        # Stage 3: Patient Verification
        await flow_manager.handle_function_call("verify_patient_identity", {"is_appropriate_person": True})
        stages_visited.append(flow_manager.current_stage)

        # Stage 4: Feedback Collection
        await flow_manager.handle_function_call("record_feedback", {
            "satisfaction_rating": 9,
            "specific_concerns": "",
            "side_effects": "",
            "experience_quality": "Great experience"
        })
        stages_visited.append(flow_manager.current_stage)

        # Stage 5: Urgency Detection
        await flow_manager.handle_function_call("detect_urgency", {"urgent_keywords": []})
        stages_visited.append(flow_manager.current_stage)

        # Stage 6: Call Completion
        await flow_manager.handle_function_call("end_call", {"acknowledged": True})

        # Assert
        assert stages_visited == [
            "greeting",
            "language_selection",
            "patient_verification",
            "feedback_collection",
            "urgency_detection",
            "call_completion"
        ]
        assert flow_manager.is_complete is True
        assert flow_manager.state.get("greeted") is True
        assert flow_manager.state.get("verified") is True
        assert flow_manager.state.get("completed") is True


class TestTwilioIntegration:
    """T048: Integration test for Twilio integration."""

    @patch.dict('os.environ', {
        'TWILIO_ACCOUNT_SID': 'ACtest123',
        'TWILIO_AUTH_TOKEN': 'test_token',
        'TWILIO_PHONE_NUMBER': '+15551234567'
    })
    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    def test_twilio_client_initialization(self, mock_client_class):
        """Test TwilioIntegration initializes with env vars."""
        # Act
        twilio = TwilioIntegration()

        # Assert
        assert twilio.account_sid == 'ACtest123'
        assert twilio.auth_token == 'test_token'
        assert twilio.phone_number == '+15551234567'
        mock_client_class.assert_called_once_with('ACtest123', 'test_token')

    @patch.dict('os.environ', {
        'TWILIO_ACCOUNT_SID': 'ACtest123',
        'TWILIO_AUTH_TOKEN': 'test_token',
        'TWILIO_PHONE_NUMBER': '+15551234567'
    })
    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    def test_initiate_call_success(self, mock_client_class):
        """Test initiating outbound call via Twilio."""
        # Arrange
        mock_call = Mock()
        mock_call.sid = "CA1234567890abcdef"
        mock_call.status = "queued"
        mock_client_class.return_value.calls.create.return_value = mock_call

        twilio = TwilioIntegration()

        # Act
        result = twilio.initiate_call(
            to_number="+12025551234",
            campaign_id="campaign_123",
            patient_phone="+12025551234",
            language="en"
        )

        # Assert
        assert result["call_sid"] == "CA1234567890abcdef"
        assert result["status"] == "queued"
        assert result["to"] == "+12025551234"
        mock_client_class.return_value.calls.create.assert_called_once()

    @patch.dict('os.environ', {
        'TWILIO_ACCOUNT_SID': 'ACtest123',
        'TWILIO_AUTH_TOKEN': 'test_token',
        'TWILIO_PHONE_NUMBER': '+15551234567'
    })
    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    def test_parse_status_callback(self, mock_client_class):
        """Test parsing Twilio status callback parameters."""
        # Arrange
        twilio = TwilioIntegration()
        webhook_data = {
            "CallSid": "CA1234567890abcdef",
            "CallStatus": "completed",
            "CallDuration": "200",
            "From": "+15551234567",
            "To": "+12025551234",
            "Direction": "outbound-api"
        }

        # Act
        result = twilio.parse_status_callback(webhook_data)

        # Assert
        assert result["call_sid"] == "CA1234567890abcdef"
        assert result["call_status"] == "completed"
        assert result["call_duration"] == "200"
        assert result["from"] == "+15551234567"
        assert result["to"] == "+12025551234"

    @patch.dict('os.environ', {
        'TWILIO_ACCOUNT_SID': 'ACtest123',
        'TWILIO_AUTH_TOKEN': 'test_token',
        'TWILIO_PHONE_NUMBER': '+15551234567'
    })
    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    def test_validate_webhook_invalid_signature(self, mock_client_class):
        """Test Twilio webhook signature validation fails with invalid signature."""
        # Arrange
        twilio = TwilioIntegration()

        # Act
        is_valid = twilio.validate_webhook(
            url="https://example.com/api/v1/webhooks/twilio/status",
            params={"CallSid": "CA123", "CallStatus": "completed"},
            signature="invalid_signature"
        )

        # Assert
        assert is_valid is False

    @patch.dict('os.environ', {
        'TWILIO_ACCOUNT_SID': 'ACtest123',
        'TWILIO_AUTH_TOKEN': 'test_token',
        'TWILIO_PHONE_NUMBER': '+15551234567'
    })
    @patch('backend.app.domains.patient_feedback.twilio_integration.Client')
    def test_parse_media_stream_start(self, mock_client_class):
        """Test parsing Twilio Media Stream start event."""
        # Arrange
        twilio = TwilioIntegration()
        start_message = {
            "event": "start",
            "start": {
                "callSid": "CA1234567890abcdef",
                "streamSid": "MZ9876543210fedcba",
                "accountSid": "ACtest123",
                "customParameters": {
                    "campaign_id": "campaign_123",
                    "patient_phone": "+12025551234",
                    "language": "es"
                },
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1
                }
            }
        }

        # Act
        result = twilio.parse_media_stream_start(start_message)

        # Assert
        assert result["call_sid"] == "CA1234567890abcdef"
        assert result["stream_sid"] == "MZ9876543210fedcba"
        assert result["campaign_id"] == "campaign_123"
        assert result["patient_phone"] == "+12025551234"
        assert result["language"] == "es"


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestUrgencyDetector:
    """T049: Integration test for urgency detection."""

    # Override the module-level asyncio mark for sync tests
    pytestmark = []

    def test_detector_initialization(self):
        """Test UrgencyDetector initializes with default keywords."""
        # Act
        detector = UrgencyDetector()

        # Assert
        assert "hospital" in detector.keywords
        assert "severe" in detector.keywords
        assert "emergency" in detector.keywords
        assert "911" in detector.keywords

    def test_detector_with_custom_keywords(self):
        """Test UrgencyDetector accepts custom keywords."""
        # Act
        detector = UrgencyDetector(custom_keywords=["custom_keyword", "another_keyword"])

        # Assert
        assert "custom_keyword" in detector.keywords
        assert "another_keyword" in detector.keywords
        assert "hospital" in detector.keywords  # Default still present

    def test_scan_detects_urgency_keywords(self):
        """Test scan() detects urgency keywords in text."""
        # Arrange
        detector = UrgencyDetector()

        # Test cases with urgency keywords
        urgent_phrases = [
            ("I went to the hospital last night", ["hospital"]),
            ("I'm experiencing severe pain", ["severe", "severe pain"]),
            ("I can't breathe properly", ["can't breathe"]),
            ("I need to go to the emergency room", ["emergency", "emergency room"]),
            ("I called 911 yesterday", ["911"]),
            ("Having an allergic reaction", ["allergic reaction"]),
        ]

        # Act & Assert
        for phrase, expected_keywords in urgent_phrases:
            result = detector.scan(phrase)
            assert len(result) > 0, f"Expected keywords in: {phrase}"
            for keyword in expected_keywords:
                # At least one expected keyword should be found
                found = any(keyword in r for r in result)
                assert found or keyword in result, f"Expected '{keyword}' in results for: {phrase}"

    def test_scan_no_urgency_in_normal_feedback(self):
        """Test scan() returns empty for normal feedback."""
        # Arrange
        detector = UrgencyDetector()

        normal_phrases = [
            "My experience was good overall",
            "The staff was friendly and helpful",
            "I rate my visit 8 out of 10",
            "Everything went smoothly",
            "No concerns or issues",
        ]

        # Act & Assert
        for phrase in normal_phrases:
            result = detector.scan(phrase)
            assert len(result) == 0, f"Unexpected keywords in: {phrase}, found: {result}"

    def test_is_urgent_returns_boolean(self):
        """Test is_urgent() returns correct boolean."""
        # Arrange
        detector = UrgencyDetector()

        # Act & Assert
        assert detector.is_urgent("I went to the hospital") is True
        assert detector.is_urgent("Everything is fine") is False
        assert detector.is_urgent("I had severe chest pain") is True
        assert detector.is_urgent("Good experience overall") is False

    def test_scan_is_case_insensitive(self):
        """Test urgency detection is case-insensitive."""
        # Arrange
        detector = UrgencyDetector()

        test_phrases = [
            "I went to the HOSPITAL",
            "SEVERE pain in my chest",
            "Can't BREATHE properly",
            "EMERGENCY situation",
        ]

        # Act & Assert
        for phrase in test_phrases:
            result = detector.scan(phrase)
            assert len(result) > 0, f"Case-insensitive match failed for: {phrase}"

    def test_scan_uses_word_boundaries(self):
        """Test scan uses word boundaries to avoid false positives."""
        # Arrange
        detector = UrgencyDetector()

        # "server" should not match "severe"
        result = detector.scan("The server was slow")
        assert "severe" not in result

        # "hospitality" should not match "hospital"
        result = detector.scan("The hospitality was great")
        assert "hospital" not in result

    def test_scan_multiple_keywords_detected(self):
        """Test detection of multiple urgency keywords in single phrase."""
        # Arrange
        detector = UrgencyDetector()

        phrase = "I had severe pain and went to the hospital emergency room"

        # Act
        result = detector.scan(phrase)

        # Assert
        assert len(result) >= 2  # Should find multiple keywords
        # Check that at least some expected keywords are found
        found_keywords = set(result)
        expected = {"severe", "hospital", "emergency", "severe pain", "emergency room"}
        assert len(found_keywords & expected) >= 2

    def test_scan_transcript(self):
        """Test scan_transcript scans only patient turns."""
        # Arrange
        detector = UrgencyDetector()

        transcript = [
            {"speaker": "ai", "text": "How was your experience?"},
            {"speaker": "patient", "text": "It was okay at first"},
            {"speaker": "ai", "text": "Did you experience any side effects?"},
            {"speaker": "patient", "text": "Yes, I had severe allergic reaction and went to emergency"},
            {"speaker": "ai", "text": "Thank you for sharing that"},
        ]

        # Act
        result = detector.scan_transcript(transcript)

        # Assert
        assert len(result) >= 1  # Should find urgency keywords
        # Should only scan patient turns, not AI turns
        assert "severe" in result or "emergency" in result or "allergic reaction" in result

    def test_scan_transcript_removes_duplicates(self):
        """Test scan_transcript removes duplicate keywords."""
        # Arrange
        detector = UrgencyDetector()

        transcript = [
            {"speaker": "patient", "text": "I went to the hospital"},
            {"speaker": "patient", "text": "The hospital was crowded"},
        ]

        # Act
        result = detector.scan_transcript(transcript)

        # Assert - "hospital" should appear only once
        assert result.count("hospital") == 1

    def test_scan_empty_text(self):
        """Test scan handles empty text gracefully."""
        # Arrange
        detector = UrgencyDetector()

        # Act & Assert
        assert detector.scan("") == []
        assert detector.scan(None) == []
        assert detector.is_urgent("") is False
