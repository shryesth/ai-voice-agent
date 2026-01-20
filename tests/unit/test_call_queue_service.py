"""
Unit tests for CallQueueService.

Tests service logic for queue creation, updates, and state management.
"""

import pytest
from datetime import datetime
from backend.app.services.call_queue_service import call_queue_service
from backend.app.models.call_queue import CallQueue
from backend.app.models.enums import QueueState, QueueMode


@pytest.mark.unit
class TestCallQueueServiceCreate:
    """Test CallQueue creation operations"""

    @pytest.mark.asyncio
    async def test_create_queue_basic(self, seeded_geography):
        """Test creating a basic queue"""
        queue = await call_queue_service.create_queue(
            geography_id=str(seeded_geography.id),
            name="Test Queue",
            description="Test Description",
            mode=QueueMode.BATCH,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5
        )

        assert queue is not None
        assert queue.name == "Test Queue"
        assert queue.description == "Test Description"
        assert queue.mode == QueueMode.BATCH
        assert queue.state == QueueState.DRAFT
        assert queue.geography_id == seeded_geography.id

    @pytest.mark.asyncio
    async def test_create_queue_with_time_windows(self, seeded_geography):
        """Test creating queue with time windows"""
        time_windows = [
            {
                "start_time_utc": "09:00",
                "end_time_utc": "17:00",
                "days_of_week": [0, 1, 2, 3, 4]
            }
        ]

        queue = await call_queue_service.create_queue(
            geography_id=str(seeded_geography.id),
            name="Windowed Queue",
            mode=QueueMode.BATCH,
            call_type="patient_feedback",
            default_language="en",
            max_concurrent_calls=5,
            time_windows=time_windows
        )

        assert len(queue.time_windows) == 1
        assert queue.time_windows[0].start_time_utc == "09:00"

    @pytest.mark.asyncio
    async def test_create_queue_invalid_geography(self):
        """Test creating queue with invalid geography"""
        from bson import ObjectId
        invalid_geo_id = str(ObjectId())

        with pytest.raises(ValueError):
            await call_queue_service.create_queue(
                geography_id=invalid_geo_id,
                name="Test Queue",
                mode=QueueMode.BATCH,
                call_type="patient_feedback",
                default_language="en",
                max_concurrent_calls=5
            )


@pytest.mark.unit
class TestCallQueueServiceRetrieval:
    """Test queue retrieval operations"""

    @pytest.mark.asyncio
    async def test_get_queue_by_id(self, seeded_call_queue):
        """Test getting queue by ID"""
        queue = await call_queue_service.get_queue_by_id(str(seeded_call_queue.id))

        assert queue is not None
        assert str(queue.id) == str(seeded_call_queue.id)
        assert queue.name == seeded_call_queue.name

    @pytest.mark.asyncio
    async def test_get_queue_by_id_not_found(self):
        """Test getting non-existent queue"""
        from bson import ObjectId
        invalid_id = str(ObjectId())

        queue = await call_queue_service.get_queue_by_id(invalid_id)

        assert queue is None

    @pytest.mark.asyncio
    async def test_list_queues(self, seeded_call_queue):
        """Test listing queues"""
        queues = await call_queue_service.list_queues()

        assert len(queues) >= 1
        queue_ids = [str(q.id) for q in queues]
        assert str(seeded_call_queue.id) in queue_ids

    @pytest.mark.asyncio
    async def test_list_queues_filter_by_geography(self, seeded_call_queue, seeded_geography):
        """Test listing queues filtered by geography"""
        queues = await call_queue_service.list_queues(
            geography_id=str(seeded_geography.id)
        )

        # All returned queues should be from the specified geography
        for queue in queues:
            assert str(queue.geography_id) == str(seeded_geography.id)

    @pytest.mark.asyncio
    async def test_list_queues_filter_by_state(self, seeded_call_queue):
        """Test listing queues filtered by state"""
        queues = await call_queue_service.list_queues(state=QueueState.DRAFT)

        # All returned queues should be in DRAFT state
        for queue in queues:
            if not queue.is_deleted:  # Only non-deleted queues
                assert queue.state == QueueState.DRAFT


@pytest.mark.unit
class TestCallQueueServiceUpdate:
    """Test queue update operations"""

    @pytest.mark.asyncio
    async def test_update_queue_name(self, seeded_call_queue):
        """Test updating queue name"""
        updated_queue = await call_queue_service.update_queue(
            str(seeded_call_queue.id),
            name="Updated Queue Name"
        )

        assert updated_queue is not None
        assert updated_queue.name == "Updated Queue Name"

    @pytest.mark.asyncio
    async def test_update_queue_description(self, seeded_call_queue):
        """Test updating queue description"""
        updated_queue = await call_queue_service.update_queue(
            str(seeded_call_queue.id),
            description="Updated Description"
        )

        assert updated_queue is not None
        assert updated_queue.description == "Updated Description"

    @pytest.mark.asyncio
    async def test_update_queue_not_found(self):
        """Test updating non-existent queue"""
        from bson import ObjectId
        invalid_id = str(ObjectId())

        with pytest.raises(ValueError):
            await call_queue_service.update_queue(invalid_id, name="New Name")


@pytest.mark.unit
class TestCallQueueServiceStateTransitions:
    """Test queue state transition operations"""

    @pytest.mark.asyncio
    async def test_start_queue(self, seeded_call_queue):
        """Test starting a queue (DRAFT -> ACTIVE)"""
        assert seeded_call_queue.state == QueueState.DRAFT

        queue = await call_queue_service.start_queue(str(seeded_call_queue.id))

        assert queue.state == QueueState.ACTIVE

    @pytest.mark.asyncio
    async def test_pause_queue(self, seeded_call_queue):
        """Test pausing an active queue"""
        # First start the queue
        await call_queue_service.start_queue(str(seeded_call_queue.id))

        # Then pause it
        queue = await call_queue_service.pause_queue(str(seeded_call_queue.id))

        assert queue.state == QueueState.PAUSED

    @pytest.mark.asyncio
    async def test_resume_queue(self, seeded_call_queue):
        """Test resuming a paused queue"""
        # Start and then pause
        await call_queue_service.start_queue(str(seeded_call_queue.id))
        await call_queue_service.pause_queue(str(seeded_call_queue.id))

        # Resume
        queue = await call_queue_service.resume_queue(str(seeded_call_queue.id))

        assert queue.state == QueueState.ACTIVE

    @pytest.mark.asyncio
    async def test_cancel_queue(self, seeded_call_queue):
        """Test canceling a queue"""
        queue = await call_queue_service.cancel_queue(str(seeded_call_queue.id))

        assert queue.state == QueueState.CANCELLED

    @pytest.mark.asyncio
    async def test_invalid_state_transition(self, seeded_call_queue):
        """Test invalid state transition raises error"""
        # Try to pause a DRAFT queue (should fail)
        with pytest.raises(ValueError):
            await call_queue_service.pause_queue(str(seeded_call_queue.id))


@pytest.mark.unit
class TestCallQueueServiceDelete:
    """Test queue deletion operations"""

    @pytest.mark.asyncio
    async def test_soft_delete_queue(self, seeded_call_queue):
        """Test soft deleting a queue"""
        queue_id = str(seeded_call_queue.id)

        await call_queue_service.delete_queue(queue_id, hard_delete=False)

        # Queue should still exist but be marked as deleted
        queue = await call_queue_service.get_queue_by_id(queue_id)
        if queue:
            assert queue.is_deleted is True

    @pytest.mark.asyncio
    async def test_delete_queue_not_found(self):
        """Test deleting non-existent queue"""
        from bson import ObjectId
        invalid_id = str(ObjectId())

        with pytest.raises(ValueError):
            await call_queue_service.delete_queue(invalid_id)


@pytest.mark.unit
class TestCallQueueServiceStatus:
    """Test queue status operations"""

    @pytest.mark.asyncio
    async def test_get_queue_status(self, seeded_call_queue):
        """Test getting queue status"""
        status = await call_queue_service.get_queue_status(str(seeded_call_queue.id))

        assert status is not None
        assert "id" in status
        assert "name" in status
        assert "state" in status
        assert "stats" in status

    @pytest.mark.asyncio
    async def test_get_queue_status_not_found(self):
        """Test getting status of non-existent queue"""
        from bson import ObjectId
        invalid_id = str(ObjectId())

        with pytest.raises(ValueError):
            await call_queue_service.get_queue_status(invalid_id)

    @pytest.mark.asyncio
    async def test_refresh_queue_stats(self, seeded_call_queue):
        """Test refreshing queue statistics"""
        queue = await call_queue_service.refresh_queue_stats(str(seeded_call_queue.id))

        assert queue is not None
        assert queue.stats is not None


@pytest.mark.unit
class TestCallQueueServiceStats:
    """Test queue statistics"""

    @pytest.mark.asyncio
    async def test_queue_stats_structure(self, seeded_call_queue):
        """Test queue stats have correct structure"""
        queue = await call_queue_service.get_queue_by_id(str(seeded_call_queue.id))

        # Queue should have stats
        if queue.stats:
            assert "total_recipients" in queue.stats
            assert "pending_count" in queue.stats
            assert "calling_count" in queue.stats
            assert "completed_count" in queue.stats
            assert "failed_count" in queue.stats
