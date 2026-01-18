"""
Integration tests for OpenAI Realtime API prewarmer.

Tests prewarmer lifecycle, connection management, and metrics tracking.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.app.services.openai_realtime_prewarmer import (
    OpenAIRealtimePrewarmer,
    ConnectionState,
    PrewarmConnection
)


@pytest.fixture
def mock_settings():
    """Mock settings for prewarmer tests"""
    with patch("backend.app.services.openai_realtime_prewarmer.settings") as mock:
        mock.openai_realtime_prewarmer_enabled = True
        mock.openai_realtime_prewarmer_timeout_ms = 30000
        mock.openai_realtime_prewarmer_cleanup_interval_ms = 5000
        mock.openai_realtime_prewarmer_connect_timeout_ms = 5000
        mock.openai_realtime_prewarmer_max_retries = 3
        mock.openai_api_key = "test_api_key"
        mock.openai_model = "gpt-4o-realtime-preview-2024-12-17"
        yield mock


@pytest.fixture
async def prewarmer(mock_settings):
    """Create and cleanup prewarmer instance"""
    prewarmer = OpenAIRealtimePrewarmer()
    yield prewarmer
    # Cleanup
    if prewarmer._running:
        await prewarmer.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_realtime_prewarmer_lifecycle(prewarmer):
    """Test Realtime API prewarmer start and stop"""
    # Start prewarmer
    await prewarmer.start()
    assert prewarmer._running is True, "Prewarmer should be running after start"
    assert prewarmer._cleanup_task is not None, "Cleanup task should be created"

    # Stop prewarmer
    await prewarmer.stop()
    assert prewarmer._running is False, "Prewarmer should be stopped"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prewarmer_disabled_state(mock_settings):
    """Test prewarmer when disabled"""
    mock_settings.openai_realtime_prewarmer_enabled = False
    prewarmer = OpenAIRealtimePrewarmer()

    assert prewarmer.enabled is False, "Prewarmer should be disabled"

    # Pre-acquire should return False when disabled
    success = await prewarmer.pre_acquire_connection(
        call_sid="test_call_123",
        voice="alloy",
        instructions="Test instructions",
        tools=[],
        temperature=0.8
    )

    assert success is False, "Pre-acquire should fail when prewarmer is disabled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pre_acquire_realtime_connection_mocked(prewarmer):
    """Test pre-acquiring OpenAI Realtime API connection (mocked WebSocket)"""
    # Mock WebSocket connection
    mock_websocket = AsyncMock()
    mock_websocket.recv = AsyncMock(return_value='{"type": "session.updated"}')
    mock_websocket.send = AsyncMock()
    mock_websocket.closed = False

    with patch("backend.app.services.openai_realtime_prewarmer.websockets.connect") as mock_connect:
        mock_connect.return_value = mock_websocket

        await prewarmer.start()

        success = await prewarmer.pre_acquire_connection(
            call_sid="test_call_123",
            voice="alloy",
            instructions="Test instructions",
            tools=[],
            temperature=0.8
        )

        assert success is True, "Pre-acquisition should succeed with mocked WebSocket"
        assert prewarmer._metrics.pre_acquired == 1, "Metrics should track pre-acquisition"

        # Check connection is in pool
        assert "test_call_123" in prewarmer._connections
        conn = prewarmer._connections["test_call_123"]
        assert conn.state == ConnectionState.CONFIGURED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_acquire_connection(prewarmer):
    """Test acquiring a pre-warmed connection"""
    # Mock WebSocket connection
    mock_websocket = AsyncMock()
    mock_websocket.recv = AsyncMock(return_value='{"type": "session.updated"}')
    mock_websocket.send = AsyncMock()
    mock_websocket.closed = False

    with patch("backend.app.services.openai_realtime_prewarmer.websockets.connect") as mock_connect:
        mock_connect.return_value = mock_websocket

        await prewarmer.start()

        # Pre-acquire connection
        await prewarmer.pre_acquire_connection(
            call_sid="test_call_456",
            voice="alloy",
            instructions="Test",
            tools=[],
            temperature=0.8
        )

        # Acquire connection
        conn, reason = await prewarmer.acquire_connection("test_call_456")

        assert conn is not None, "Connection should be acquired"
        assert reason == "success", "Acquisition reason should be success"
        assert conn.state == ConnectionState.USED, "Connection state should be USED"
        assert prewarmer._metrics.used == 1, "Metrics should track usage"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_acquire_nonexistent_connection(prewarmer):
    """Test acquiring a connection that doesn't exist"""
    await prewarmer.start()

    conn, reason = await prewarmer.acquire_connection("nonexistent_call")

    assert conn is None, "Connection should be None for nonexistent call"
    assert reason == "not_found", "Reason should be not_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_realtime_prewarmer_metrics(prewarmer):
    """Test Realtime API prewarmer metrics tracking"""
    # Mock WebSocket connection
    mock_websocket = AsyncMock()
    mock_websocket.recv = AsyncMock(return_value='{"type": "session.updated"}')
    mock_websocket.send = AsyncMock()
    mock_websocket.closed = False

    with patch("backend.app.services.openai_realtime_prewarmer.websockets.connect") as mock_connect:
        mock_connect.return_value = mock_websocket

        await prewarmer.start()

        await prewarmer.pre_acquire_connection("test_call_789", "alloy", "Test", [], 0.8)

        metrics = prewarmer.get_metrics()

        assert metrics["enabled"] is True
        assert metrics["pre_acquired"] == 1
        assert metrics["used"] == 0
        assert metrics["expired"] == 0
        assert metrics["failed"] == 0
        assert metrics["active_connections"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures(prewarmer):
    """Test circuit breaker opens after consecutive failures"""
    # Mock WebSocket to always fail
    with patch("backend.app.services.openai_realtime_prewarmer.websockets.connect") as mock_connect:
        mock_connect.side_effect = Exception("Connection failed")

        await prewarmer.start()

        # Trigger 5 failures to open circuit breaker
        for i in range(5):
            success = await prewarmer.pre_acquire_connection(
                call_sid=f"test_call_{i}",
                voice="alloy",
                instructions="Test",
                tools=[],
                temperature=0.8
            )
            assert success is False, f"Pre-acquisition {i} should fail"

        # Check circuit breaker is open
        assert prewarmer._circuit_breaker.is_open() is True, "Circuit breaker should be open"

        # Next pre-acquisition should be rejected by circuit breaker
        success = await prewarmer.pre_acquire_connection(
            call_sid="test_call_6",
            voice="alloy",
            instructions="Test",
            tools=[],
            temperature=0.8
        )

        assert success is False, "Pre-acquisition should be rejected by open circuit breaker"
        assert prewarmer._metrics.circuit_breaks >= 1, "Metrics should track circuit breaks"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_expired_connections(prewarmer):
    """Test cleanup of expired connections"""
    # Set very short timeout for testing
    prewarmer.timeout_ms = 100  # 100ms timeout

    # Mock WebSocket connection
    mock_websocket = AsyncMock()
    mock_websocket.recv = AsyncMock(return_value='{"type": "session.updated"}')
    mock_websocket.send = AsyncMock()
    mock_websocket.closed = False
    mock_websocket.close = AsyncMock()

    with patch("backend.app.services.openai_realtime_prewarmer.websockets.connect") as mock_connect:
        mock_connect.return_value = mock_websocket

        await prewarmer.start()

        # Pre-acquire connection
        await prewarmer.pre_acquire_connection(
            call_sid="test_call_expire",
            voice="alloy",
            instructions="Test",
            tools=[],
            temperature=0.8
        )

        assert len(prewarmer._connections) == 1, "Should have 1 connection"

        # Wait for connection to expire
        await asyncio.sleep(0.2)  # Wait 200ms (> 100ms timeout)

        # Manually trigger cleanup
        await prewarmer._cleanup_expired_connections()

        assert len(prewarmer._connections) == 0, "Expired connection should be cleaned up"
        assert prewarmer._metrics.expired >= 1, "Metrics should track expired connections"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_context_manager_acquire(prewarmer):
    """Test context manager for acquiring connections"""
    # Mock WebSocket connection
    mock_websocket = AsyncMock()
    mock_websocket.recv = AsyncMock(return_value='{"type": "session.updated"}')
    mock_websocket.send = AsyncMock()
    mock_websocket.closed = False

    with patch("backend.app.services.openai_realtime_prewarmer.websockets.connect") as mock_connect:
        mock_connect.return_value = mock_websocket

        await prewarmer.start()

        # Pre-acquire connection
        await prewarmer.pre_acquire_connection(
            call_sid="test_call_context",
            voice="alloy",
            instructions="Test",
            tools=[],
            temperature=0.8
        )

        # Use context manager
        async with prewarmer.acquire("test_call_context") as conn:
            assert conn is not None, "Connection should be acquired via context manager"
            assert conn.state == ConnectionState.USED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_logic_with_exponential_backoff(prewarmer):
    """Test retry logic with exponential backoff"""
    call_count = 0

    async def failing_connect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception(f"Connection failed attempt {call_count}")
        # Succeed on 3rd attempt
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value='{"type": "session.updated"}')
        mock_ws.send = AsyncMock()
        mock_ws.closed = False
        return mock_ws

    with patch("backend.app.services.openai_realtime_prewarmer.websockets.connect") as mock_connect:
        mock_connect.side_effect = failing_connect

        await prewarmer.start()

        success = await prewarmer.pre_acquire_connection(
            call_sid="test_call_retry",
            voice="alloy",
            instructions="Test",
            tools=[],
            temperature=0.8
        )

        assert success is True, "Pre-acquisition should succeed after retries"
        assert call_count == 3, "Should have retried 2 times before succeeding"
        assert prewarmer._metrics.retries >= 2, "Metrics should track retries"
