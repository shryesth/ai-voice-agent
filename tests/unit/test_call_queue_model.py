"""
Unit tests for CallQueue model.

Tests model logic including state transitions, validation, and helper methods.
"""

import pytest
from backend.app.models.call_queue import CallQueue, TimeWindow, RetryStrategy, ClaritySyncConfig, can_transition_to
from backend.app.models.enums import QueueState, QueueMode


@pytest.mark.unit
class TestCallQueueStateTransitions:
    """Test state transition validation"""

    def test_can_transition_draft_to_active(self):
        """Test DRAFT -> ACTIVE transition is valid"""
        assert can_transition_to(QueueState.DRAFT, QueueState.ACTIVE) is True

    def test_can_transition_draft_to_cancelled(self):
        """Test DRAFT -> CANCELLED transition is valid"""
        assert can_transition_to(QueueState.DRAFT, QueueState.CANCELLED) is True

    def test_cannot_transition_draft_to_paused(self):
        """Test DRAFT -> PAUSED is invalid"""
        assert can_transition_to(QueueState.DRAFT, QueueState.PAUSED) is False

    def test_can_transition_active_to_paused(self):
        """Test ACTIVE -> PAUSED transition is valid"""
        assert can_transition_to(QueueState.ACTIVE, QueueState.PAUSED) is True

    def test_can_transition_active_to_completed(self):
        """Test ACTIVE -> COMPLETED transition is valid"""
        assert can_transition_to(QueueState.ACTIVE, QueueState.COMPLETED) is True

    def test_can_transition_active_to_cancelled(self):
        """Test ACTIVE -> CANCELLED transition is valid"""
        assert can_transition_to(QueueState.ACTIVE, QueueState.CANCELLED) is True

    def test_can_transition_paused_to_active(self):
        """Test PAUSED -> ACTIVE transition is valid"""
        assert can_transition_to(QueueState.PAUSED, QueueState.ACTIVE) is True

    def test_can_transition_paused_to_cancelled(self):
        """Test PAUSED -> CANCELLED transition is valid"""
        assert can_transition_to(QueueState.PAUSED, QueueState.CANCELLED) is True

    def test_cannot_transition_from_completed(self):
        """Test COMPLETED is terminal state"""
        assert can_transition_to(QueueState.COMPLETED, QueueState.ACTIVE) is False
        assert can_transition_to(QueueState.COMPLETED, QueueState.PAUSED) is False
        assert can_transition_to(QueueState.COMPLETED, QueueState.CANCELLED) is False

    def test_cannot_transition_from_cancelled(self):
        """Test CANCELLED is terminal state"""
        assert can_transition_to(QueueState.CANCELLED, QueueState.ACTIVE) is False
        assert can_transition_to(QueueState.CANCELLED, QueueState.PAUSED) is False
        assert can_transition_to(QueueState.CANCELLED, QueueState.COMPLETED) is False


@pytest.mark.unit
class TestTimeWindowValidation:
    """Test TimeWindow validation"""

    def test_time_window_valid_format(self):
        """Test valid time window format"""
        tw = TimeWindow(
            start_time_utc="09:00",
            end_time_utc="17:00",
            days_of_week=[0, 1, 2, 3, 4]
        )

        assert tw.start_time_utc == "09:00"
        assert tw.end_time_utc == "17:00"
        assert tw.days_of_week == [0, 1, 2, 3, 4]

    def test_time_window_default_days(self):
        """Test default days are Mon-Fri"""
        tw = TimeWindow(
            start_time_utc="09:00",
            end_time_utc="17:00"
        )

        assert tw.days_of_week == [0, 1, 2, 3, 4]

    def test_time_window_24_7(self):
        """Test 24/7 time window"""
        tw = TimeWindow(
            start_time_utc="00:00",
            end_time_utc="23:59",
            days_of_week=[0, 1, 2, 3, 4, 5, 6]
        )

        assert tw.start_time_utc == "00:00"
        assert tw.end_time_utc == "23:59"
        assert len(tw.days_of_week) == 7

    def test_time_window_midnight_hour(self):
        """Test time window with midnight hours"""
        tw = TimeWindow(
            start_time_utc="00:00",
            end_time_utc="06:00",
            days_of_week=[1, 2, 3]
        )

        assert tw.start_time_utc == "00:00"
        assert tw.end_time_utc == "06:00"

    def test_time_window_late_evening(self):
        """Test time window in late evening"""
        tw = TimeWindow(
            start_time_utc="20:00",
            end_time_utc="23:59"
        )

        assert tw.start_time_utc == "20:00"
        assert tw.end_time_utc == "23:59"


@pytest.mark.unit
class TestRetryStrategyValidation:
    """Test RetryStrategy validation and defaults"""

    def test_retry_strategy_defaults(self):
        """Test default retry strategy values"""
        rs = RetryStrategy()

        assert rs.max_retries == 3
        assert rs.exponential_backoff is True
        assert rs.no_answer_delay == 1800  # 30 min
        assert rs.busy_delay == 3600  # 1 hour
        assert rs.voicemail_delay == 7200  # 2 hours
        assert rs.timeout_delay == 1800  # 30 min

    def test_retry_strategy_custom_max_retries(self):
        """Test custom max retries"""
        rs = RetryStrategy(max_retries=5)

        assert rs.max_retries == 5

    def test_retry_strategy_no_exponential_backoff(self):
        """Test disabling exponential backoff"""
        rs = RetryStrategy(exponential_backoff=False)

        assert rs.exponential_backoff is False

    def test_retry_strategy_custom_delays(self):
        """Test custom failure-specific delays"""
        rs = RetryStrategy(
            no_answer_delay=3600,
            busy_delay=7200,
            voicemail_delay=900
        )

        assert rs.no_answer_delay == 3600
        assert rs.busy_delay == 7200
        assert rs.voicemail_delay == 900

    def test_retry_strategy_max_retries_boundary(self):
        """Test max retries boundary conditions"""
        # Valid: 0
        rs = RetryStrategy(max_retries=0)
        assert rs.max_retries == 0

        # Valid: 10
        rs = RetryStrategy(max_retries=10)
        assert rs.max_retries == 10


@pytest.mark.unit
class TestClaritySyncConfigValidation:
    """Test ClaritySyncConfig validation"""

    def test_clarity_sync_disabled_by_default(self):
        """Test Clarity sync is disabled by default"""
        csc = ClaritySyncConfig()

        assert csc.enabled is False

    def test_clarity_sync_enabled(self):
        """Test enabling Clarity sync"""
        csc = ClaritySyncConfig(enabled=True)

        assert csc.enabled is True

    def test_clarity_sync_interval_default(self):
        """Test default sync interval"""
        csc = ClaritySyncConfig()

        assert csc.sync_interval_minutes == 5

    def test_clarity_sync_interval_custom(self):
        """Test custom sync interval"""
        csc = ClaritySyncConfig(sync_interval_minutes=15)

        assert csc.sync_interval_minutes == 15

    def test_clarity_sync_max_per_sync_default(self):
        """Test default max per sync"""
        csc = ClaritySyncConfig()

        assert csc.max_per_sync == 100

    def test_clarity_sync_max_per_sync_custom(self):
        """Test custom max per sync"""
        csc = ClaritySyncConfig(max_per_sync=500)

        assert csc.max_per_sync == 500


@pytest.mark.unit
class TestCallQueueCreation:
    """Test CallQueue model creation and basic functionality"""

    @pytest.mark.asyncio
    async def test_create_call_queue_basic(self, seeded_geography):
        """Test creating a CallQueue with basic fields"""
        queue = CallQueue(
            name="Test Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.BATCH,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5
        )

        assert queue.name == "Test Queue"
        assert queue.geography_id == seeded_geography.id
        assert queue.mode == QueueMode.BATCH
        assert queue.state == QueueState.DRAFT
        assert queue.call_type == "patient_feedback"
        assert queue.default_language == "en"
        assert queue.max_concurrent_calls == 5

    @pytest.mark.asyncio
    async def test_call_queue_with_time_windows(self, seeded_geography):
        """Test CallQueue with time windows"""
        time_windows = [
            TimeWindow(
                start_time_utc="09:00",
                end_time_utc="17:00",
                days_of_week=[0, 1, 2, 3, 4]
            )
        ]

        queue = CallQueue(
            name="Time Windowed Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.FOREVER,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5,
            time_windows=time_windows
        )

        assert len(queue.time_windows) == 1
        assert queue.time_windows[0].start_time_utc == "09:00"

    @pytest.mark.asyncio
    async def test_call_queue_with_retry_strategy(self, seeded_geography):
        """Test CallQueue with custom retry strategy"""
        retry_strategy = RetryStrategy(
            max_retries=5,
            exponential_backoff=True
        )

        queue = CallQueue(
            name="Custom Retry Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.BATCH,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5,
            retry_strategy=retry_strategy
        )

        assert queue.retry_strategy.max_retries == 5

    @pytest.mark.asyncio
    async def test_call_queue_with_clarity_sync(self, seeded_geography):
        """Test CallQueue with Clarity sync configuration"""
        clarity_sync = ClaritySyncConfig(
            enabled=True,
            sync_interval_minutes=10
        )

        queue = CallQueue(
            name="Clarity Synced Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.FOREVER,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5,
            clarity_sync=clarity_sync
        )

        assert queue.clarity_sync.enabled is True
        assert queue.clarity_sync.sync_interval_minutes == 10


@pytest.mark.unit
class TestCallQueueDefaults:
    """Test CallQueue default values"""

    @pytest.mark.asyncio
    async def test_call_queue_default_is_deleted_false(self, seeded_geography):
        """Test default is_deleted is False"""
        queue = CallQueue(
            name="Test Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.BATCH,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5
        )

        assert queue.is_deleted is False

    @pytest.mark.asyncio
    async def test_call_queue_default_empty_time_windows(self, seeded_geography):
        """Test default empty time windows means 24/7"""
        queue = CallQueue(
            name="Test Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.BATCH,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5
        )

        assert queue.time_windows == []

    @pytest.mark.asyncio
    async def test_call_queue_default_retry_strategy(self, seeded_geography):
        """Test default retry strategy is created"""
        queue = CallQueue(
            name="Test Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.BATCH,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5
        )

        assert queue.retry_strategy is not None
        assert queue.retry_strategy.max_retries == 3

    @pytest.mark.asyncio
    async def test_call_queue_created_at_set(self, seeded_geography):
        """Test created_at timestamp is set"""
        queue = CallQueue(
            name="Test Queue",
            geography_id=seeded_geography.id,
            mode=QueueMode.BATCH,
            state=QueueState.DRAFT,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5
        )

        assert queue.created_at is not None
