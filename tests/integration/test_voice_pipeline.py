"""
Integration tests for voice pipeline (User Story 4).

Tests the complete voice call workflow:
- T047: FlowManager state management for 6-stage conversation flow
- T048: Twilio integration (call initiation, webhook handling)
- T049: Urgency detection (keyword matching)

Note: These tests require valid Twilio credentials to pass.
In development, they can be run with mocked Twilio responses.
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from backend.app.domains.patient_feedback.flow_manager import FlowManager
from backend.app.domains.patient_feedback.function_registry import FunctionRegistry
from backend.app.domains.patient_feedback.urgency_detector import UrgencyDetector
from backend.app.domains.patient_feedback.twilio_integration import TwilioIntegration


pytestmark = pytest.mark.asyncio


class TestFlowManager:
    """T047: Integration test for FlowManager state management."""

    async def test_flow_manager_initialization(self):
        """Test FlowManager initializes with correct starting state."""
        # Act
        flow_manager = FlowManager()
        await flow_manager.initialize()

        # Assert
        assert flow_manager.current_stage == "confirm_guardian"
        assert flow_manager._initialized is True
        assert flow_manager.is_complete is False
        assert flow_manager.state.get("completed_stages") == []

    async def test_flow_manager_state_tracking(self):
        """Test FlowManager tracks state updates correctly."""
        # Arrange
        flow_manager = FlowManager()
        await flow_manager.initialize()

        # Act - Simulate state updates from FunctionRegistry handlers
        flow_manager.state["guardian_confirmed"] = True
        flow_manager.state["current_stage"] = "confirm_visit"
        flow_manager.state["completed_stages"] = ["confirm_guardian"]

        # Assert
        assert flow_manager.current_stage == "confirm_visit"
        assert flow_manager.state.get("guardian_confirmed") is True
        assert "confirm_guardian" in flow_manager.state.get("completed_stages", [])

    async def test_flow_manager_completion(self):
        """Test FlowManager marks flow as complete."""
        # Arrange
        flow_manager = FlowManager()
        await flow_manager.initialize()

        # Act - Simulate completion
        flow_manager.state["completed"] = True
        flow_manager.state["completion_reason"] = "complete"

        # Assert
        assert flow_manager.is_complete is True

    async def test_get_conversation_data(self):
        """Test get_conversation_data returns collected data."""
        # Arrange
        flow_manager = FlowManager()
        await flow_manager.initialize()

        # Simulate full conversation data
        flow_manager.state.update({
            "guardian_confirmed": True,
            "visit_confirmed": True,
            "service_confirmed": True,
            "has_side_effects": False,
            "side_effects_details": "",
            "satisfaction_rating": 8,
            "completed": True,
            "completion_reason": "complete",
            "completed_stages": ["confirm_guardian", "confirm_visit", "confirm_service", "record_satisfaction", "end_call"]
        })

        # Act
        data = flow_manager.get_conversation_data()

        # Assert
        assert data["guardian_confirmed"] is True
        assert data["visit_confirmed"] is True
        assert data["service_confirmed"] is True
        assert data["satisfaction_rating"] == 8
        assert data["completed"] is True
        assert len(data["completed_stages"]) == 5


class TestFunctionRegistry:
    """Integration tests for FunctionRegistry function handlers."""

    @pytest.fixture
    def setup_registry(self):
        """Create FlowManager and FunctionRegistry for testing."""
        flow_manager = FlowManager()
        call_record = Mock()
        call_record.event_info = {"event_type": "vaccination", "vaccine_name": "Flu Shot"}
        registry = FunctionRegistry(flow_manager, call_record)

        # Mock task for queuing frames
        mock_task = AsyncMock()
        registry.set_task(mock_task)

        return flow_manager, registry, mock_task

    async def test_get_all_tools(self, setup_registry):
        """Test get_all_tools returns all 6 function definitions."""
        flow_manager, registry, _ = setup_registry

        # Act
        tools = registry.get_all_tools()

        # Assert
        assert len(tools) == 6
        tool_names = [t["function"]["name"] for t in tools]
        assert "confirm_guardian" in tool_names
        assert "confirm_visit" in tool_names
        assert "confirm_service" in tool_names
        assert "record_side_effects" in tool_names
        assert "record_satisfaction" in tool_names
        assert "end_call" in tool_names

    async def test_confirm_guardian_success(self, setup_registry):
        """Test confirm_guardian handler updates state on confirmation."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()

        # Mock FunctionCallParams
        mock_params = Mock()
        mock_params.arguments = {"confirmed": True}
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_confirm_guardian(mock_params)

        # Assert
        assert flow_manager.state["guardian_confirmed"] is True
        assert flow_manager.state["current_stage"] == "confirm_visit"
        assert "confirm_guardian" in flow_manager.state["completed_stages"]
        mock_params.result_callback.assert_called_once()
        call_args = mock_params.result_callback.call_args[0][0]
        assert call_args["status"] == "confirmed"

    async def test_confirm_guardian_retry(self, setup_registry):
        """Test confirm_guardian handler handles retries."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()

        mock_params = Mock()
        mock_params.arguments = {"confirmed": False}
        mock_params.result_callback = AsyncMock()

        # Act - First rejection
        await registry._handle_confirm_guardian(mock_params)

        # Assert
        assert flow_manager.state["guardian_retry_count"] == 1
        assert flow_manager.state.get("completed") is not True
        call_args = mock_params.result_callback.call_args[0][0]
        assert call_args["status"] == "retry"

    async def test_confirm_guardian_max_retries(self, setup_registry):
        """Test confirm_guardian ends call after max retries."""
        flow_manager, registry, mock_task = setup_registry
        await flow_manager.initialize()
        flow_manager.state["guardian_retry_count"] = 1  # Already had one retry

        mock_params = Mock()
        mock_params.arguments = {"confirmed": False}
        mock_params.result_callback = AsyncMock()

        # Act - Second rejection (hits max retries)
        await registry._handle_confirm_guardian(mock_params)

        # Assert
        assert flow_manager.state["completed"] is True
        assert flow_manager.state["completion_reason"] == "wrong_person_max_retries"
        mock_task.queue_frames.assert_called_once()  # Should queue EndFrame

    async def test_confirm_visit_success(self, setup_registry):
        """Test confirm_visit handler updates state."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()

        mock_params = Mock()
        mock_params.arguments = {"confirmed": True}
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_confirm_visit(mock_params)

        # Assert
        assert flow_manager.state["visit_confirmed"] is True
        assert flow_manager.state["current_stage"] == "confirm_service"
        assert "confirm_visit" in flow_manager.state["completed_stages"]

    async def test_confirm_service_vaccination_flow(self, setup_registry):
        """Test confirm_service proceeds to side_effects for vaccination events."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()
        flow_manager.state["event_info"] = {"event_type": "vaccination"}

        mock_params = Mock()
        mock_params.arguments = {"confirmed": True}
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_confirm_service(mock_params)

        # Assert
        assert flow_manager.state["service_confirmed"] is True
        assert flow_manager.state["current_stage"] == "record_side_effects"
        call_args = mock_params.result_callback.call_args[0][0]
        assert call_args["is_vaccination"] is True

    async def test_confirm_service_non_vaccination_flow(self, setup_registry):
        """Test confirm_service skips side_effects for non-vaccination events."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()
        flow_manager.state["event_info"] = {"event_type": "checkup"}

        mock_params = Mock()
        mock_params.arguments = {"confirmed": True}
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_confirm_service(mock_params)

        # Assert
        assert flow_manager.state["current_stage"] == "record_satisfaction"
        call_args = mock_params.result_callback.call_args[0][0]
        assert call_args["is_vaccination"] is False

    async def test_record_side_effects_severe(self, setup_registry):
        """Test record_side_effects flags severe symptoms."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()

        mock_params = Mock()
        mock_params.arguments = {
            "has_side_effects": True,
            "details": "I had difficulty breathing and went to the hospital"
        }
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_record_side_effects(mock_params)

        # Assert
        assert flow_manager.state["has_side_effects"] is True
        assert flow_manager.state["severe_side_effects"] is True
        assert flow_manager.state["urgency_flagged"] is True
        assert flow_manager.state["current_stage"] == "record_satisfaction"

    async def test_record_satisfaction(self, setup_registry):
        """Test record_satisfaction stores rating."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()

        mock_params = Mock()
        mock_params.arguments = {"rating": 9}
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_record_satisfaction(mock_params)

        # Assert
        assert flow_manager.state["satisfaction_rating"] == 9
        assert flow_manager.state["current_stage"] == "end_call"
        assert flow_manager.state.get("low_satisfaction_followup") is not True

    async def test_record_satisfaction_low_rating(self, setup_registry):
        """Test record_satisfaction flags low ratings."""
        flow_manager, registry, _ = setup_registry
        await flow_manager.initialize()

        mock_params = Mock()
        mock_params.arguments = {"rating": 2}
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_record_satisfaction(mock_params)

        # Assert
        assert flow_manager.state["satisfaction_rating"] == 2
        assert flow_manager.state["low_satisfaction_followup"] is True

    async def test_end_call(self, setup_registry):
        """Test end_call queues goodbye and EndFrame."""
        flow_manager, registry, mock_task = setup_registry
        await flow_manager.initialize()

        mock_params = Mock()
        mock_params.arguments = {"reason": "complete"}
        mock_params.result_callback = AsyncMock()

        # Act
        await registry._handle_end_call(mock_params)

        # Assert
        assert flow_manager.state["completed"] is True
        assert flow_manager.state["completion_reason"] == "complete"
        mock_task.queue_frames.assert_called_once()
        call_args = mock_params.result_callback.call_args[0][0]
        assert call_args["status"] == "ended"


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
