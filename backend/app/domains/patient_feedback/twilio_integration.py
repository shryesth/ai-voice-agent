"""
Twilio integration for outbound patient feedback calls.

Handles:
- Call initiation via Twilio API
- WebSocket Media Stream setup
- Status webhook validation
"""

from typing import Optional, Dict, Any
from twilio.rest import Client
from twilio.request_validator import RequestValidator
import logging

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class TwilioIntegration:
    """
    Twilio integration for voice calls.
    
    Manages outbound call initiation and webhook validation.
    Uses TwiML to connect calls to FastAPI WebSocket endpoint.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        phone_number: Optional[str] = None,
        websocket_url: Optional[str] = None
    ):
        """
        Initialize Twilio client.

        Args:
            account_sid: Twilio Account SID (defaults to settings)
            auth_token: Twilio Auth Token (defaults to settings)
            phone_number: Twilio phone number (defaults to settings)
            websocket_url: WebSocket URL for media streaming (defaults to settings)
        """
        self.account_sid = account_sid or settings.twilio_account_sid
        self.auth_token = auth_token or settings.twilio_auth_token
        self.phone_number = phone_number or settings.twilio_phone_number
        self.websocket_url = websocket_url or settings.twilio_websocket_url

        if not all([self.account_sid, self.auth_token, self.phone_number]):
            raise ValueError("Missing required Twilio credentials")

        self.client = Client(self.account_sid, self.auth_token)
        self.validator = RequestValidator(self.auth_token)

    def initiate_call(
        self,
        to_number: str,
        campaign_id: str,
        patient_phone: str,
        language: str = "en",
        status_callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate outbound call to patient.

        Args:
            to_number: Patient phone number (E.164 format)
            campaign_id: Campaign ID for tracking
            patient_phone: Patient phone for tracking
            language: Preferred language (en, es, fr, ht)
            status_callback_url: URL for status callbacks

        Returns:
            Dict with call_sid, status, and metadata
        """
        # Build TwiML to connect call to WebSocket
        twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{self.websocket_url}">
            <Parameter name="campaign_id" value="{campaign_id}" />
            <Parameter name="patient_phone" value="{patient_phone}" />
            <Parameter name="language" value="{language}" />
        </Stream>
    </Connect>
</Response>'''

        try:
            call = self.client.calls.create(
                to=to_number,
                from_=self.phone_number,
                twiml=twiml,
                status_callback=status_callback_url,
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                status_callback_method="POST",
                timeout=30,  # Ring timeout in seconds
                record=False  # Don't record calls (we have transcript)
            )

            logger.info(f"Twilio call initiated: {call.sid} to {to_number}")

            return {
                "call_sid": call.sid,
                "status": call.status,
                "to": to_number,
                "from": self.phone_number,
                "direction": "outbound-api"
            }

        except Exception as e:
            logger.error(f"Failed to initiate Twilio call: {e}")
            raise

    def validate_webhook(
        self,
        url: str,
        params: Dict[str, str],
        signature: str
    ) -> bool:
        """
        Validate Twilio webhook signature.

        Args:
            url: Full URL of the webhook endpoint
            params: Request parameters (form data)
            signature: X-Twilio-Signature header value

        Returns:
            True if signature is valid
        """
        return self.validator.validate(url, params, signature)

    def parse_status_callback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Twilio status callback parameters.

        Args:
            params: Webhook form parameters

        Returns:
            Parsed status data
        """
        return {
            "call_sid": params.get("CallSid"),
            "call_status": params.get("CallStatus"),
            "call_duration": params.get("CallDuration"),
            "from": params.get("From"),
            "to": params.get("To"),
            "direction": params.get("Direction"),
            "timestamp": params.get("Timestamp")
        }

    def parse_media_stream_start(self, start_message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Twilio Media Stream 'start' event.

        Args:
            start_message: WebSocket start message from Twilio

        Returns:
            Parsed stream metadata
        """
        start_data = start_message.get("start", {})
        custom_params = start_data.get("customParameters", {})

        return {
            "call_sid": start_data.get("callSid"),
            "stream_sid": start_data.get("streamSid"),
            "account_sid": start_data.get("accountSid"),
            "campaign_id": custom_params.get("campaign_id"),
            "patient_phone": custom_params.get("patient_phone"),
            "language": custom_params.get("language", "en"),
            "media_format": start_data.get("mediaFormat", {})
        }
