"""
OpenAI Realtime API Connection Prewarmer.

Pre-warms WebSocket connections to the OpenAI Realtime API to reduce call initiation latency.
Implements circuit breaker pattern, retry logic, and connection lifecycle management.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, List, Tuple, Any
import websockets
from websockets.client import WebSocketClientProtocol

from backend.app.core.config import settings


logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """Connection lifecycle states"""
    PENDING = "pending"
    CONNECTED = "connected"
    CONFIGURED = "configured"
    USED = "used"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class PrewarmConnection:
    """Pre-warmed OpenAI Realtime API connection"""
    call_sid: str
    websocket: Optional[WebSocketClientProtocol]
    state: ConnectionState
    created_at: datetime
    voice: str
    instructions: str
    tools: List[Dict[str, Any]]
    temperature: float
    buffered_messages: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def is_expired(self, timeout_ms: int) -> bool:
        """Check if connection has expired"""
        age_ms = (datetime.utcnow() - self.created_at).total_seconds() * 1000
        return age_ms > timeout_ms

    def get_buffered_messages(self) -> List[Dict[str, Any]]:
        """Get and clear buffered messages"""
        messages = self.buffered_messages.copy()
        self.buffered_messages.clear()
        return messages


@dataclass
class PrewarmerMetrics:
    """Metrics for prewarmer performance tracking"""
    pre_acquired: int = 0
    used: int = 0
    expired: int = 0
    failed: int = 0
    circuit_breaks: int = 0
    retries: int = 0
    total_latency_saved_ms: float = 0.0

    @property
    def usage_rate_percent(self) -> float:
        """Percentage of pre-acquired connections that were actually used"""
        if self.pre_acquired == 0:
            return 0.0
        return (self.used / self.pre_acquired) * 100

    @property
    def waste_rate_percent(self) -> float:
        """Percentage of pre-acquired connections that expired unused"""
        if self.pre_acquired == 0:
            return 0.0
        return (self.expired / self.pre_acquired) * 100

    @property
    def avg_latency_saved_ms(self) -> float:
        """Average latency saved per used connection"""
        if self.used == 0:
            return 0.0
        return self.total_latency_saved_ms / self.used


class CircuitBreaker:
    """Circuit breaker to prevent hammering failed API"""
    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failures = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open

    def record_success(self):
        """Record successful operation"""
        self.failures = 0
        self.state = "closed"

    def record_failure(self):
        """Record failed operation"""
        self.failures += 1
        self.last_failure_time = datetime.utcnow()
        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failures} failures")

    def is_open(self) -> bool:
        """Check if circuit breaker is open"""
        if self.state == "closed":
            return False

        if self.state == "open":
            # Check if timeout has elapsed to move to half-open
            if self.last_failure_time:
                elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
                if elapsed > self.timeout_seconds:
                    self.state = "half-open"
                    logger.info("Circuit breaker moved to half-open state")
                    return False
            return True

        # half-open state - allow one request through
        return False


class OpenAIRealtimePrewarmer:
    """OpenAI Realtime API Connection Prewarmer"""

    OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"

    def __init__(self):
        self.enabled = settings.openai_realtime_prewarmer_enabled
        self.timeout_ms = settings.openai_realtime_prewarmer_timeout_ms
        self.cleanup_interval_ms = settings.openai_realtime_prewarmer_cleanup_interval_ms
        self.connect_timeout_ms = settings.openai_realtime_prewarmer_connect_timeout_ms
        self.max_retries = settings.openai_realtime_prewarmer_max_retries
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model

        # Connection pool
        self._connections: Dict[str, PrewarmConnection] = {}
        self._lock = asyncio.Lock()

        # Lifecycle management
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

        # Circuit breaker
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, timeout_seconds=60)

        # Metrics
        self._metrics = PrewarmerMetrics()

        logger.info(f"OpenAI Realtime Prewarmer initialized (enabled={self.enabled})")

    async def start(self):
        """Start the prewarmer cleanup loop"""
        if not self.enabled:
            logger.info("OpenAI Realtime Prewarmer is disabled")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("OpenAI Realtime Prewarmer started")

    async def stop(self):
        """Stop the prewarmer and close all connections"""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        async with self._lock:
            for call_sid, conn in self._connections.items():
                if conn.websocket and not conn.websocket.closed:
                    try:
                        await conn.websocket.close()
                    except Exception as e:
                        logger.error(f"Error closing connection for {call_sid}: {e}")
            self._connections.clear()

        logger.info("OpenAI Realtime Prewarmer stopped")

    async def pre_acquire_connection(
        self,
        call_sid: str,
        voice: str,
        instructions: str,
        tools: List[Dict[str, Any]],
        temperature: float
    ) -> bool:
        """
        Pre-acquire a Realtime API connection for a call.

        Args:
            call_sid: Unique call identifier
            voice: OpenAI Realtime voice (alloy, shimmer, nova, echo)
            instructions: System instructions
            tools: Available tools configuration
            temperature: Response temperature

        Returns:
            True if connection was successfully pre-acquired
        """
        if not self.enabled:
            return False

        # Check circuit breaker
        if self._circuit_breaker.is_open():
            logger.warning(f"Circuit breaker open, skipping pre-acquisition for {call_sid}")
            self._metrics.circuit_breaks += 1
            return False

        # Retry with exponential backoff
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    self._metrics.retries += 1
                    backoff_ms = min(1000 * (2 ** attempt), 10000)  # Max 10s backoff
                    logger.info(f"Retry {attempt} for {call_sid} after {backoff_ms}ms")
                    await asyncio.sleep(backoff_ms / 1000)

                # Create connection
                conn = await self._create_connection(call_sid, voice, instructions, tools, temperature)

                if conn.state == ConnectionState.CONFIGURED:
                    async with self._lock:
                        self._connections[call_sid] = conn

                    self._metrics.pre_acquired += 1
                    self._circuit_breaker.record_success()
                    logger.info(f"Pre-acquired Realtime API connection for {call_sid}")
                    return True
                else:
                    logger.warning(f"Connection for {call_sid} not configured: {conn.state}")

            except Exception as e:
                logger.error(f"Pre-acquisition attempt {attempt + 1} failed for {call_sid}: {e}")
                self._circuit_breaker.record_failure()

                if attempt == self.max_retries - 1:
                    self._metrics.failed += 1
                    return False

        return False

    async def _create_connection(
        self,
        call_sid: str,
        voice: str,
        instructions: str,
        tools: List[Dict[str, Any]],
        temperature: float
    ) -> PrewarmConnection:
        """Create and configure a Realtime API WebSocket connection"""
        conn = PrewarmConnection(
            call_sid=call_sid,
            websocket=None,
            state=ConnectionState.PENDING,
            created_at=datetime.utcnow(),
            voice=voice,
            instructions=instructions,
            tools=tools,
            temperature=temperature
        )

        try:
            # Connect to OpenAI Realtime API
            url = f"{self.OPENAI_REALTIME_URL}?model={self.model}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }

            conn.websocket = await asyncio.wait_for(
                websockets.connect(url, extra_headers=headers),
                timeout=self.connect_timeout_ms / 1000
            )
            conn.state = ConnectionState.CONNECTED
            logger.debug(f"Connected to OpenAI Realtime API for {call_sid}")

            # Configure session
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "voice": voice,
                    "instructions": instructions,
                    "tools": tools,
                    "temperature": temperature,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    }
                }
            }

            await conn.websocket.send(json.dumps(session_config))

            # Wait for session.updated confirmation
            response = await asyncio.wait_for(
                conn.websocket.recv(),
                timeout=5.0
            )
            response_data = json.loads(response)

            if response_data.get("type") == "session.updated":
                conn.state = ConnectionState.CONFIGURED
                logger.debug(f"Session configured for {call_sid}")
            else:
                logger.warning(f"Unexpected response: {response_data.get('type')}")
                conn.state = ConnectionState.FAILED
                conn.error = f"Unexpected response type: {response_data.get('type')}"

        except asyncio.TimeoutError:
            conn.state = ConnectionState.FAILED
            conn.error = "Connection timeout"
            logger.error(f"Timeout connecting/configuring Realtime API for {call_sid}")
        except Exception as e:
            conn.state = ConnectionState.FAILED
            conn.error = str(e)
            logger.error(f"Error creating connection for {call_sid}: {e}")

        return conn

    async def acquire_connection(self, call_sid: str) -> Tuple[Optional[PrewarmConnection], str]:
        """
        Acquire a pre-warmed connection for use.

        Args:
            call_sid: Call identifier

        Returns:
            Tuple of (connection, reason)
            - connection: PrewarmConnection if available, None otherwise
            - reason: String explaining why connection was/wasn't available
        """
        async with self._lock:
            conn = self._connections.get(call_sid)

            if not conn:
                return None, "not_found"

            if conn.state != ConnectionState.CONFIGURED:
                return None, f"invalid_state_{conn.state}"

            if conn.is_expired(self.timeout_ms):
                conn.state = ConnectionState.EXPIRED
                self._metrics.expired += 1
                return None, "expired"

            # Mark as used
            conn.state = ConnectionState.USED
            self._metrics.used += 1

            # Estimate latency saved (typical: 500-2000ms)
            estimated_latency_saved = 1000  # Conservative estimate
            self._metrics.total_latency_saved_ms += estimated_latency_saved

            return conn, "success"

    async def _cleanup_loop(self):
        """Periodic cleanup of expired connections"""
        interval_seconds = self.cleanup_interval_ms / 1000

        while self._running:
            try:
                await asyncio.sleep(interval_seconds)
                await self._cleanup_expired_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_expired_connections(self):
        """Remove expired connections from pool"""
        async with self._lock:
            expired_sids = []

            for call_sid, conn in self._connections.items():
                if conn.is_expired(self.timeout_ms) and conn.state != ConnectionState.USED:
                    expired_sids.append(call_sid)
                    conn.state = ConnectionState.EXPIRED
                    self._metrics.expired += 1

                    # Close WebSocket
                    if conn.websocket and not conn.websocket.closed:
                        try:
                            await conn.websocket.close()
                        except Exception as e:
                            logger.error(f"Error closing expired connection {call_sid}: {e}")

            # Remove from pool
            for call_sid in expired_sids:
                del self._connections[call_sid]

            if expired_sids:
                logger.info(f"Cleaned up {len(expired_sids)} expired connections")

    def get_metrics(self) -> Dict[str, Any]:
        """Get prewarmer performance metrics"""
        return {
            "enabled": self.enabled,
            "pre_acquired": self._metrics.pre_acquired,
            "used": self._metrics.used,
            "expired": self._metrics.expired,
            "failed": self._metrics.failed,
            "circuit_breaks": self._metrics.circuit_breaks,
            "retries": self._metrics.retries,
            "usage_rate_percent": round(self._metrics.usage_rate_percent, 2),
            "waste_rate_percent": round(self._metrics.waste_rate_percent, 2),
            "total_latency_saved_ms": round(self._metrics.total_latency_saved_ms, 2),
            "avg_latency_saved_ms": round(self._metrics.avg_latency_saved_ms, 2),
            "circuit_breaker_state": self._circuit_breaker.state,
            "active_connections": len(self._connections),
            "timeout_ms": self.timeout_ms
        }

    @asynccontextmanager
    async def acquire(self, call_sid: str):
        """
        Context manager for acquiring pre-warmed connection.

        Usage:
            async with prewarmer.acquire(call_sid) as conn:
                if conn:
                    # Use pre-warmed connection
                else:
                    # Fallback to fresh connection
        """
        conn, reason = await self.acquire_connection(call_sid)

        try:
            yield conn
        finally:
            # Cleanup handled elsewhere
            pass
