"""
Contract tests for CallQueue API endpoints.

Tests verify the API contract for call queue management, state transitions,
and queue operations.
"""

import pytest
from httpx import AsyncClient
from bson import ObjectId


@pytest.mark.contract
class TestCallQueueCreate:
    """Test POST /api/v1/geographies/{geography_id}/queues"""

    @pytest.mark.asyncio
    async def test_create_queue_success(self, async_client: AsyncClient, auth_headers: dict, seeded_geography):
        """Test successful queue creation with all fields"""
        response = await async_client.post(
            f"/api/v1/geographies/{seeded_geography.id}/queues",
            headers=auth_headers,
            json={
                "name": "Test Queue",
                "description": "Test queue for automated tests",
                "mode": "batch",
                "call_type": "patient_feedback",
                "default_language": "en",
                "max_concurrent_calls": 5,
                "time_windows": [
                    {
                        "start_time_utc": "09:00",
                        "end_time_utc": "17:00",
                        "days_of_week": [0, 1, 2, 3, 4]
                    }
                ],
                "retry_strategy": {
                    "max_retries": 3,
                    "exponential_backoff": True
                },
                "nexus_sync": {
                    "enabled": False
                }
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert data["name"] == "Test Queue"
        assert data["description"] == "Test queue for automated tests"
        assert data["mode"] == "batch"
        assert data["call_type"] == "patient_feedback"
        assert data["default_language"] == "en"
        assert data["max_concurrent_calls"] == 5
        assert data["state"] == "draft"

        # Verify time windows
        assert len(data["time_windows"]) == 1
        assert data["time_windows"][0]["start_time_utc"] == "09:00"
        assert data["time_windows"][0]["end_time_utc"] == "17:00"
        assert data["time_windows"][0]["days_of_week"] == [0, 1, 2, 3, 4]

        # Verify retry strategy
        assert data["retry_strategy"]["max_retries"] == 3
        assert data["retry_strategy"]["exponential_backoff"] is True

    @pytest.mark.asyncio
    async def test_create_queue_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_geography):
        """Test that non-admin users cannot create queues"""
        response = await async_client.post(
            f"/api/v1/geographies/{seeded_geography.id}/queues",
            headers=user_auth_headers,
            json={
                "name": "Unauthorized Queue",
                "mode": "batch",
                "call_type": "patient_feedback",
                "default_language": "en",
                "max_concurrent_calls": 5,
                "retry_strategy": {},
                "nexus_sync": {}
            }
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_queue_invalid_geography(self, async_client: AsyncClient, auth_headers: dict):
        """Test queue creation with invalid geography ID"""
        invalid_id = str(ObjectId())
        response = await async_client.post(
            f"/api/v1/geographies/{invalid_id}/queues",
            headers=auth_headers,
            json={
                "name": "Test Queue",
                "mode": "batch",
                "call_type": "patient_feedback",
                "default_language": "en",
                "max_concurrent_calls": 5,
                "retry_strategy": {},
                "nexus_sync": {}
            }
        )

        assert response.status_code == 400


@pytest.mark.contract
class TestCallQueueList:
    """Test GET /api/v1/queues"""

    @pytest.mark.asyncio
    async def test_list_queues_success(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test listing queues"""
        response = await async_client.get(
            "/api/v1/queues",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

        # Verify list contains created queue
        queue_ids = [q["id"] for q in data["items"]]
        assert str(seeded_call_queue.id) in queue_ids

    @pytest.mark.asyncio
    async def test_list_queues_with_geography_filter(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue, seeded_geography):
        """Test listing queues filtered by geography"""
        response = await async_client.get(
            f"/api/v1/queues?geography_id={seeded_geography.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # All returned queues should be from the specified geography
        for queue in data["items"]:
            assert queue["geography_id"] == str(seeded_geography.id)

    @pytest.mark.asyncio
    async def test_list_queues_with_state_filter(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test listing queues filtered by state"""
        response = await async_client.get(
            "/api/v1/queues?state=draft",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # All returned queues should be in draft state
        for queue in data["items"]:
            assert queue["state"] == "draft"

    @pytest.mark.asyncio
    async def test_list_queues_pagination(self, async_client: AsyncClient, auth_headers: dict):
        """Test queue listing with pagination"""
        response = await async_client.get(
            "/api/v1/queues?skip=0&limit=10",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["skip"] == 0
        assert data["limit"] == 10
        assert len(data["items"]) <= 10


@pytest.mark.contract
class TestCallQueueGet:
    """Test GET /api/v1/queues/{queue_id}"""

    @pytest.mark.asyncio
    async def test_get_queue_success(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test retrieving a queue by ID"""
        response = await async_client.get(
            f"/api/v1/queues/{seeded_call_queue.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(seeded_call_queue.id)
        assert data["name"] == seeded_call_queue.name
        assert data["state"] == seeded_call_queue.state.value

    @pytest.mark.asyncio
    async def test_get_queue_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test retrieving non-existent queue"""
        invalid_id = str(ObjectId())
        response = await async_client.get(
            f"/api/v1/queues/{invalid_id}",
            headers=auth_headers
        )

        assert response.status_code == 404


@pytest.mark.contract
class TestCallQueueUpdate:
    """Test PATCH /api/v1/queues/{queue_id}"""

    @pytest.mark.asyncio
    async def test_update_queue_success(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test updating queue details"""
        response = await async_client.patch(
            f"/api/v1/queues/{seeded_call_queue.id}",
            headers=auth_headers,
            json={
                "name": "Updated Queue Name",
                "description": "Updated description"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "Updated Queue Name"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_queue_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot update queues"""
        response = await async_client.patch(
            f"/api/v1/queues/{seeded_call_queue.id}",
            headers=user_auth_headers,
            json={
                "name": "Unauthorized Update"
            }
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_queue_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test updating non-existent queue"""
        invalid_id = str(ObjectId())
        response = await async_client.patch(
            f"/api/v1/queues/{invalid_id}",
            headers=auth_headers,
            json={
                "name": "Updated Name"
            }
        )

        assert response.status_code == 404


@pytest.mark.contract
class TestCallQueueDelete:
    """Test DELETE /api/v1/queues/{queue_id}"""

    @pytest.mark.asyncio
    async def test_delete_queue_soft_delete(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test soft-deleting a queue"""
        queue_id = seeded_call_queue.id

        response = await async_client.delete(
            f"/api/v1/queues/{queue_id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify queue still exists but is marked as deleted
        get_response = await async_client.get(
            f"/api/v1/queues/{queue_id}",
            headers=auth_headers
        )

        # After soft delete, queue should still be retrievable with is_deleted flag
        if get_response.status_code == 200:
            data = get_response.json()
            assert data.get("is_deleted", False) is True

    @pytest.mark.asyncio
    async def test_delete_queue_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot delete queues"""
        response = await async_client.delete(
            f"/api/v1/queues/{seeded_call_queue.id}",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestCallQueueStateTransitions:
    """Test state transition endpoints"""

    @pytest.mark.asyncio
    async def test_start_queue_draft_to_active(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test starting a queue (DRAFT -> ACTIVE)"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/start",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["previous_state"] == "draft"
        assert data["new_state"] == "active"
        assert "changed_at" in data

    @pytest.mark.asyncio
    async def test_pause_queue_active_to_paused(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test pausing a queue (ACTIVE -> PAUSED)"""
        # First start the queue
        await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/start",
            headers=auth_headers
        )

        # Then pause it
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/pause",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["previous_state"] == "active"
        assert data["new_state"] == "paused"

    @pytest.mark.asyncio
    async def test_resume_queue_paused_to_active(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test resuming a queue (PAUSED -> ACTIVE)"""
        # Start then pause
        await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/start",
            headers=auth_headers
        )
        await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/pause",
            headers=auth_headers
        )

        # Resume
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/resume",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["previous_state"] == "paused"
        assert data["new_state"] == "active"

    @pytest.mark.asyncio
    async def test_cancel_queue(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test canceling a queue"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/cancel",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["new_state"] == "cancelled"

    @pytest.mark.asyncio
    async def test_state_transition_invalid(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test invalid state transition"""
        # Try to pause a DRAFT queue (invalid)
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/pause",
            headers=auth_headers
        )

        # Should fail
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_state_transition_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot transition states"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/start",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestCallQueueStatus:
    """Test GET /api/v1/queues/{queue_id}/status"""

    @pytest.mark.asyncio
    async def test_get_queue_status(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test retrieving queue status with statistics"""
        response = await async_client.get(
            f"/api/v1/queues/{seeded_call_queue.id}/status",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Verify status structure
        assert "id" in data
        assert "name" in data
        assert "state" in data
        assert "stats" in data

        # Verify stats structure
        stats = data["stats"]
        assert "total_recipients" in stats
        assert "pending_count" in stats
        assert "calling_count" in stats
        assert "completed_count" in stats
        assert "failed_count" in stats
        assert "dlq_count" in stats

    @pytest.mark.asyncio
    async def test_get_queue_status_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting status of non-existent queue"""
        invalid_id = str(ObjectId())
        response = await async_client.get(
            f"/api/v1/queues/{invalid_id}/status",
            headers=auth_headers
        )

        assert response.status_code == 404


@pytest.mark.contract
class TestCallQueueRefreshStats:
    """Test POST /api/v1/queues/{queue_id}/refresh-stats"""

    @pytest.mark.asyncio
    async def test_refresh_queue_stats(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test refreshing queue statistics"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/refresh-stats",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(seeded_call_queue.id)

    @pytest.mark.asyncio
    async def test_refresh_stats_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot refresh stats"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/refresh-stats",
            headers=user_auth_headers
        )

        assert response.status_code == 403
