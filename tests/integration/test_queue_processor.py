"""
Integration tests for Celery queue processor task.

Tests queue processing logic, time windows, concurrency limits,
and interaction with Beanie models in worker context.
"""

import pytest
import pytest_asyncio
from datetime import datetime, time
from unittest.mock import patch, MagicMock

from backend.app.models.campaign import Campaign, CampaignState, CampaignConfig
from backend.app.models.queue_entry import QueueEntry, QueueState
from backend.app.models.geography import Geography
from backend.app.tasks.queue_processor import process_campaign_queues, is_within_time_window


pytestmark = pytest.mark.queue


@pytest_asyncio.fixture
async def test_geography(test_db) -> Geography:
    """Create a test geography for campaigns."""
    geography = Geography(
        name="Test Region",
        region_code="US-TEST",
        retention_policy={
            "retention_days": 365,
            "compliance_notes": "Test policy"
        }
    )
    await geography.insert()
    return geography


@pytest_asyncio.fixture
async def active_campaign(test_db, test_geography) -> Campaign:
    """Create an active campaign with queue entries."""
    campaign = Campaign(
        name="Test Campaign",
        geography_id=str(test_geography.id),
        state=CampaignState.ACTIVE,
        config=CampaignConfig(
            max_concurrent_calls=5,
            patient_list=["+12025551234", "+12025555678"],
            language_preference="en",
            time_windows=[]
        )
    )
    await campaign.insert()
    return campaign


@pytest_asyncio.fixture
async def pending_queue_entries(test_db, active_campaign) -> list[QueueEntry]:
    """Create pending queue entries for testing."""
    entries = []
    for i, phone in enumerate(["+12025551234", "+12025555678", "+12025559999"]):
        entry = QueueEntry(
            campaign_id=str(active_campaign.id),
            patient_phone=phone,
            language="en",
            state=QueueState.PENDING,
            retry_count=0,
            created_at=datetime.utcnow()
        )
        await entry.insert()
        entries.append(entry)
    return entries


class TestTimeWindowValidation:
    """Test time window validation logic."""

    def test_no_time_windows_always_allowed(self):
        """When no time windows configured, processing is always allowed."""
        assert is_within_time_window([]) is True

    def test_within_single_time_window(self):
        """Test time within a single configured window."""
        # This test depends on current time, so we'll mock datetime
        with patch('backend.app.tasks.queue_processor.datetime') as mock_datetime:
            # Mock current time to 10:00 AM UTC on Monday
            mock_now = MagicMock()
            mock_now.time.return_value = time(10, 0, 0)
            mock_now.strftime.return_value = "Monday"
            mock_datetime.utcnow.return_value = mock_now

            time_windows = [{
                "start_time": time(9, 0, 0),
                "end_time": time(17, 0, 0),
                "days_of_week": ["Monday", "Tuesday", "Wednesday"]
            }]

            assert is_within_time_window(time_windows) is True

    def test_outside_time_window(self):
        """Test time outside configured window."""
        with patch('backend.app.tasks.queue_processor.datetime') as mock_datetime:
            # Mock current time to 8:00 AM UTC on Monday (before window)
            mock_now = MagicMock()
            mock_now.time.return_value = time(8, 0, 0)
            mock_now.strftime.return_value = "Monday"
            mock_datetime.utcnow.return_value = mock_now

            time_windows = [{
                "start_time": time(9, 0, 0),
                "end_time": time(17, 0, 0),
                "days_of_week": ["Monday", "Tuesday", "Wednesday"]
            }]

            assert is_within_time_window(time_windows) is False

    def test_wrong_day_of_week(self):
        """Test time window with wrong day of week."""
        with patch('backend.app.tasks.queue_processor.datetime') as mock_datetime:
            # Mock current time to Sunday (not allowed)
            mock_now = MagicMock()
            mock_now.time.return_value = time(10, 0, 0)
            mock_now.strftime.return_value = "Sunday"
            mock_datetime.utcnow.return_value = mock_now

            time_windows = [{
                "start_time": time(9, 0, 0),
                "end_time": time(17, 0, 0),
                "days_of_week": ["Monday", "Tuesday", "Wednesday"]
            }]

            assert is_within_time_window(time_windows) is False

    def test_midnight_crossing_window(self):
        """Test time window that crosses midnight."""
        with patch('backend.app.tasks.queue_processor.datetime') as mock_datetime:
            # Mock current time to 1:00 AM (after midnight)
            mock_now = MagicMock()
            mock_now.time.return_value = time(1, 0, 0)
            mock_now.strftime.return_value = "Tuesday"
            mock_datetime.utcnow.return_value = mock_now

            # Window from 22:00 to 02:00 (crosses midnight)
            time_windows = [{
                "start_time": time(22, 0, 0),
                "end_time": time(2, 0, 0),
                "days_of_week": ["Monday", "Tuesday", "Wednesday"]
            }]

            assert is_within_time_window(time_windows) is True


@pytest.mark.integration
class TestQueueProcessorTask:
    """Test queue processor Celery task."""

    @patch('backend.app.tasks.queue_processor.initiate_patient_call')
    async def test_task_registered(self, mock_call_task):
        """Test that queue processor task is registered with Celery."""
        from backend.app.celery_app import celery_app

        # Verify task is registered
        assert 'process_campaign_queues' in celery_app.tasks

        # Verify task is callable
        task = celery_app.tasks['process_campaign_queues']
        assert callable(task)

    @patch('backend.app.tasks.queue_processor.initiate_patient_call')
    async def test_process_active_campaign(
        self,
        mock_call_task,
        test_db,
        active_campaign,
        pending_queue_entries
    ):
        """Test queue processor processes entries for active campaign."""
        # Mock the delay method to avoid actually calling Celery
        mock_call_task.delay = MagicMock()

        # Run the task
        result = process_campaign_queues()

        # Verify results
        assert result["processed"] == 3  # All 3 entries processed
        assert result["campaigns"] == 1  # 1 campaign processed

        # Verify initiate_patient_call was called for each entry
        assert mock_call_task.delay.call_count == 3

    @patch('backend.app.tasks.queue_processor.initiate_patient_call')
    async def test_no_active_campaigns(self, mock_call_task, test_db):
        """Test queue processor when no active campaigns exist."""
        mock_call_task.delay = MagicMock()

        # Run the task with no campaigns
        result = process_campaign_queues()

        # Verify no processing occurred
        assert result["processed"] == 0
        assert result["campaigns"] == 0
        assert mock_call_task.delay.call_count == 0

    @patch('backend.app.tasks.queue_processor.initiate_patient_call')
    async def test_respects_concurrency_limit(
        self,
        mock_call_task,
        test_db,
        active_campaign,
        pending_queue_entries
    ):
        """Test that queue processor respects max_concurrent_calls limit."""
        mock_call_task.delay = MagicMock()

        # Set lower concurrency limit
        active_campaign.config.max_concurrent_calls = 2
        await active_campaign.save()

        # Mark 1 entry as CALLING (in progress)
        pending_queue_entries[0].state = QueueState.CALLING
        await pending_queue_entries[0].save()

        # Run the task
        result = process_campaign_queues()

        # Should only process 1 more (limit=2, 1 in progress, so 1 slot available)
        assert result["processed"] == 1
        assert mock_call_task.delay.call_count == 1

    @patch('backend.app.tasks.queue_processor.initiate_patient_call')
    @patch('backend.app.tasks.queue_processor.is_within_time_window')
    async def test_respects_time_windows(
        self,
        mock_time_window,
        mock_call_task,
        test_db,
        active_campaign,
        pending_queue_entries
    ):
        """Test that queue processor skips campaigns outside time windows."""
        mock_call_task.delay = MagicMock()
        mock_time_window.return_value = False  # Outside time window

        # Run the task
        result = process_campaign_queues()

        # Should not process any entries
        assert result["processed"] == 0
        assert mock_call_task.delay.call_count == 0

    @patch('backend.app.tasks.queue_processor.initiate_patient_call')
    async def test_updates_entry_state_to_calling(
        self,
        mock_call_task,
        test_db,
        active_campaign,
        pending_queue_entries
    ):
        """Test that queue processor updates entry state to CALLING."""
        mock_call_task.delay = MagicMock()

        # Run the task
        process_campaign_queues()

        # Verify entries were updated to CALLING
        for entry in pending_queue_entries:
            updated_entry = await QueueEntry.get(entry.id)
            assert updated_entry.state == QueueState.CALLING

    @patch('backend.app.tasks.queue_processor.initiate_patient_call')
    async def test_handles_paused_campaign(
        self,
        mock_call_task,
        test_db,
        active_campaign,
        pending_queue_entries
    ):
        """Test that queue processor skips paused campaigns."""
        mock_call_task.delay = MagicMock()

        # Pause the campaign
        active_campaign.state = CampaignState.PAUSED
        await active_campaign.save()

        # Run the task
        result = process_campaign_queues()

        # Should not process paused campaign
        assert result["processed"] == 0
        assert result["campaigns"] == 0
        assert mock_call_task.delay.call_count == 0


@pytest.mark.integration
class TestBeanieModelAccess:
    """Test that Beanie models are accessible in Celery worker context."""

    async def test_campaign_model_accessible(self, test_db, active_campaign):
        """Test that Campaign model and its fields are accessible."""
        # This would fail with AttributeError if Beanie not initialized
        campaigns = await Campaign.find(Campaign.state == CampaignState.ACTIVE).to_list()

        assert len(campaigns) == 1
        assert campaigns[0].state == CampaignState.ACTIVE
        assert campaigns[0].name == "Test Campaign"

    async def test_queue_entry_model_accessible(self, test_db, pending_queue_entries):
        """Test that QueueEntry model is accessible in worker context."""
        entries = await QueueEntry.find(QueueEntry.state == QueueState.PENDING).to_list()

        assert len(entries) == 3
        for entry in entries:
            assert entry.state == QueueState.PENDING
            assert entry.retry_count == 0

    async def test_multiple_campaigns_query(self, test_db, test_geography):
        """Test querying multiple campaigns with different states."""
        # Create campaigns with different states
        active = Campaign(
            name="Active Campaign",
            geography_id=str(test_geography.id),
            state=CampaignState.ACTIVE,
            config=CampaignConfig(max_concurrent_calls=5, patient_list=[])
        )
        await active.insert()

        paused = Campaign(
            name="Paused Campaign",
            geography_id=str(test_geography.id),
            state=CampaignState.PAUSED,
            config=CampaignConfig(max_concurrent_calls=5, patient_list=[])
        )
        await paused.insert()

        # Query by state
        active_campaigns = await Campaign.find(
            Campaign.state == CampaignState.ACTIVE
        ).to_list()

        assert len(active_campaigns) == 1
        assert active_campaigns[0].name == "Active Campaign"
