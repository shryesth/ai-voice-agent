"""
Integration tests for Celery worker initialization.

Tests that Beanie models are properly initialized in worker context,
async operations work correctly, and forward references are resolved.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime

from backend.app.models.campaign import Campaign, CampaignState, CampaignConfig
from backend.app.models.call_record import CallRecord, CallTracking
from backend.app.models.queue_entry import QueueEntry, QueueState
from backend.app.models.geography import Geography
from backend.app.models.user import User, UserRole
from backend.app.core.security import hash_password


pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def test_geography(test_db) -> Geography:
    """Create a test geography."""
    geography = Geography(
        name="Worker Test Region",
        region_code="WT-001",
        retention_policy={
            "retention_days": 365,
            "compliance_notes": "Test policy"
        }
    )
    await geography.insert()
    return geography


@pytest_asyncio.fixture
async def test_campaign(test_db, test_geography) -> Campaign:
    """Create a test campaign."""
    campaign = Campaign(
        name="Worker Test Campaign",
        geography_id=str(test_geography.id),
        state=CampaignState.DRAFT,
        config=CampaignConfig(
            max_concurrent_calls=10,
            patient_list=["+12025551111"],
            language_preference="en",
            time_windows=[]
        )
    )
    await campaign.insert()
    return campaign


class TestBeanieInitialization:
    """Test that Beanie is properly initialized in worker context."""

    async def test_campaign_state_field_accessible(self, test_db, test_campaign):
        """
        Test that Campaign.state field is accessible.

        This would fail with AttributeError if Beanie not initialized properly.
        Specifically tests the bug: AttributeError: state
        """
        # Query using the state field
        campaigns = await Campaign.find(Campaign.state == CampaignState.DRAFT).to_list()

        assert len(campaigns) >= 1
        assert campaigns[0].state == CampaignState.DRAFT

        # Verify we can access the state attribute directly
        assert hasattr(test_campaign, 'state')
        assert test_campaign.state == CampaignState.DRAFT

    async def test_all_models_initialized(self, test_db):
        """Test that all document models are initialized and accessible."""
        # Test User model
        user = User(
            email="worker@test.com",
            hashed_password=hash_password("TestPass123!"),
            role=UserRole.USER,
            is_active=True
        )
        await user.insert()
        found_user = await User.find_one(User.email == "worker@test.com")
        assert found_user is not None
        assert found_user.email == "worker@test.com"

        # Test Geography model
        geo = Geography(
            name="Test Geo",
            region_code="TG-001",
            retention_policy={"retention_days": 30}
        )
        await geo.insert()
        found_geo = await Geography.find_one(Geography.region_code == "TG-001")
        assert found_geo is not None

        # Test Campaign model
        campaign = Campaign(
            name="Test",
            geography_id=str(geo.id),
            state=CampaignState.DRAFT,
            config=CampaignConfig(max_concurrent_calls=5, patient_list=[])
        )
        await campaign.insert()
        found_campaign = await Campaign.find_one(Campaign.name == "Test")
        assert found_campaign is not None

        # Test QueueEntry model
        entry = QueueEntry(
            campaign_id=str(campaign.id),
            patient_phone="+12025550000",
            language="en",
            state=QueueState.PENDING,
            retry_count=0
        )
        await entry.insert()
        found_entry = await QueueEntry.find_one(
            QueueEntry.patient_phone == "+12025550000"
        )
        assert found_entry is not None

    async def test_beanie_queries_work(self, test_db, test_geography):
        """Test that Beanie queries work correctly in worker context."""
        # Create multiple campaigns
        for i in range(3):
            campaign = Campaign(
                name=f"Campaign {i}",
                geography_id=str(test_geography.id),
                state=CampaignState.ACTIVE if i % 2 == 0 else CampaignState.PAUSED,
                config=CampaignConfig(max_concurrent_calls=5, patient_list=[])
            )
            await campaign.insert()

        # Test filtering
        active = await Campaign.find(Campaign.state == CampaignState.ACTIVE).to_list()
        paused = await Campaign.find(Campaign.state == CampaignState.PAUSED).to_list()

        assert len(active) == 2  # Campaigns 0 and 2
        assert len(paused) == 1  # Campaign 1

    async def test_beanie_aggregations_work(self, test_db, test_campaign):
        """Test that Beanie aggregation queries work."""
        # Create multiple queue entries
        for i in range(5):
            entry = QueueEntry(
                campaign_id=str(test_campaign.id),
                patient_phone=f"+1202555{i:04d}",
                language="en",
                state=QueueState.PENDING if i < 3 else QueueState.CALLING,
                retry_count=0
            )
            await entry.insert()

        # Count entries by state
        pending_count = await QueueEntry.find(
            QueueEntry.campaign_id == str(test_campaign.id),
            QueueEntry.state == QueueState.PENDING
        ).count()

        calling_count = await QueueEntry.find(
            QueueEntry.campaign_id == str(test_campaign.id),
            QueueEntry.state == QueueState.CALLING
        ).count()

        assert pending_count == 3
        assert calling_count == 2


class TestPydanticForwardReferences:
    """Test that Pydantic forward references are resolved via model_rebuild()."""

    async def test_call_record_with_campaign_link(self, test_db, test_campaign):
        """
        Test creating CallRecord with Campaign Link.

        This would fail with PydanticUserError if model_rebuild() not called:
        "CallRecord is not fully defined; you should define Campaign,
        then call CallRecord.model_rebuild()"
        """
        # Create a CallRecord with campaign_id Link
        call_record = CallRecord(
            campaign_id=str(test_campaign.id),
            patient_phone="+12025551234",
            language="en",
            call_tracking=CallTracking(status="queued"),
            created_at=datetime.utcnow()
        )

        # This should work without PydanticUserError
        await call_record.insert()

        # Verify the record was created
        found = await CallRecord.find_one(
            CallRecord.patient_phone == "+12025551234"
        )
        assert found is not None
        assert str(found.campaign_id) == str(test_campaign.id)

    async def test_call_record_fetch_campaign_link(self, test_db, test_campaign):
        """Test fetching linked Campaign from CallRecord."""
        # Create a CallRecord
        call_record = CallRecord(
            campaign_id=str(test_campaign.id),
            patient_phone="+12025559999",
            language="en",
            call_tracking=CallTracking(status="in-progress"),
            created_at=datetime.utcnow()
        )
        await call_record.insert()

        # Fetch the call record
        found = await CallRecord.find_one(
            CallRecord.patient_phone == "+12025559999"
        )

        # The Link should be properly resolved
        assert found is not None
        assert str(found.campaign_id) == str(test_campaign.id)

        # Fetch the linked campaign
        linked_campaign = await found.campaign_id.fetch()
        assert linked_campaign is not None
        assert linked_campaign.name == test_campaign.name

    async def test_multiple_call_records_same_campaign(self, test_db, test_campaign):
        """Test creating multiple CallRecords linked to same Campaign."""
        phones = ["+12025551111", "+12025552222", "+12025553333"]

        for phone in phones:
            call_record = CallRecord(
                campaign_id=str(test_campaign.id),
                patient_phone=phone,
                language="en",
                call_tracking=CallTracking(status="queued"),
                created_at=datetime.utcnow()
            )
            await call_record.insert()

        # Query all call records for this campaign
        records = await CallRecord.find(
            CallRecord.campaign_id == str(test_campaign.id)
        ).to_list()

        assert len(records) == 3
        for record in records:
            assert str(record.campaign_id) == str(test_campaign.id)


class TestAsyncOperations:
    """Test that async operations work correctly in worker context."""

    async def test_async_event_loop_available(self):
        """
        Test that event loop is available in worker context.

        This would fail with RuntimeError if event loop not set up:
        "There is no current event loop in thread"
        """
        # This should work without RuntimeError
        loop = asyncio.get_event_loop()
        assert loop is not None
        assert loop.is_running() is False  # We're not inside run_until_complete

    async def test_run_until_complete_works(self, test_db, test_geography):
        """Test that run_until_complete works (simulating task pattern)."""
        async def fetch_geographies():
            return await Geography.find_all().to_list()

        # Simulate what Celery tasks do
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(fetch_geographies())

        assert isinstance(result, list)
        assert len(result) >= 1

    async def test_multiple_async_operations_sequential(self, test_db, test_geography):
        """Test multiple sequential async operations (like in queue_processor)."""
        # Create a campaign
        campaign = Campaign(
            name="Sequential Test",
            geography_id=str(test_geography.id),
            state=CampaignState.ACTIVE,
            config=CampaignConfig(max_concurrent_calls=5, patient_list=[])
        )
        await campaign.insert()

        # Create queue entries
        for i in range(3):
            entry = QueueEntry(
                campaign_id=str(campaign.id),
                patient_phone=f"+1202555{i:04d}",
                language="en",
                state=QueueState.PENDING,
                retry_count=0
            )
            await entry.insert()

        # Simulate queue_processor operations
        loop = asyncio.get_event_loop()

        # Find active campaigns
        active_campaigns = loop.run_until_complete(
            Campaign.find(Campaign.state == CampaignState.ACTIVE).to_list()
        )
        assert len(active_campaigns) >= 1

        # Count in-progress calls
        in_progress_count = loop.run_until_complete(
            QueueEntry.find(
                QueueEntry.campaign_id == str(campaign.id),
                QueueEntry.state == QueueState.CALLING
            ).count()
        )
        assert in_progress_count == 0

        # Get ready entries
        ready_entries = loop.run_until_complete(
            QueueEntry.find(
                QueueEntry.campaign_id == str(campaign.id),
                QueueEntry.state == QueueState.PENDING
            ).to_list()
        )
        assert len(ready_entries) == 3

        # Update entry state
        ready_entries[0].state = QueueState.CALLING
        loop.run_until_complete(ready_entries[0].save())

        # Verify update
        updated = loop.run_until_complete(
            QueueEntry.get(ready_entries[0].id)
        )
        assert updated.state == QueueState.CALLING


class TestWorkerIsolation:
    """Test that worker has proper database isolation."""

    async def test_worker_uses_correct_database(self, test_db):
        """Test that worker operations use the test database."""
        # Create a unique record
        unique_code = f"TEST-{datetime.utcnow().timestamp()}"
        geo = Geography(
            name=f"Isolation Test {unique_code}",
            region_code=unique_code,
            retention_policy={"retention_days": 30}
        )
        await geo.insert()

        # Verify it's in the test database
        found = await Geography.find_one(Geography.region_code == unique_code)
        assert found is not None
        assert found.region_code == unique_code

    async def test_database_connection_healthy(self, test_db):
        """Test that database connection is healthy in worker context."""
        from backend.app.core.database import db

        # Ping should work
        is_healthy = await db.ping()
        assert is_healthy is True
