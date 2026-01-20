"""
Contract tests for Test Call API endpoints.

Tests verify the API contract for test calls, queue debugging,
and manual queue processing.
"""

import pytest
from httpx import AsyncClient
from bson import ObjectId


@pytest.mark.contract
class TestTestCallInitiate:
    """Test POST /api/v1/test-calls/initiate"""

    @pytest.mark.asyncio
    async def test_initiate_test_call_success(self, async_client: AsyncClient, auth_headers: dict, seeded_geography):
        """Test initiating a one-off test call"""
        response = await async_client.post(
            "/api/v1/test-calls/initiate",
            headers=auth_headers,
            json={
                "geography_id": str(seeded_geography.id),
                "phone_number": "+12025551234",
                "contact_name": "Test Contact",
                "contact_type": "patient",
                "call_type": "patient_feedback",
                "language": "en",
                "patient_name": "Test Patient"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert "call_id" in data
        assert "status" in data
        assert data["phone_number"] == "+12025551234"
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_initiate_test_call_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_geography):
        """Test that non-admin users cannot initiate test calls"""
        response = await async_client.post(
            "/api/v1/test-calls/initiate",
            headers=user_auth_headers,
            json={
                "geography_id": str(seeded_geography.id),
                "phone_number": "+12025551234",
                "contact_name": "Test Contact",
                "contact_type": "patient",
                "call_type": "patient_feedback",
                "language": "en"
            }
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_initiate_test_call_invalid_geography(self, async_client: AsyncClient, auth_headers: dict):
        """Test initiating test call with invalid geography"""
        invalid_id = str(ObjectId())
        response = await async_client.post(
            "/api/v1/test-calls/initiate",
            headers=auth_headers,
            json={
                "geography_id": invalid_id,
                "phone_number": "+12025551234",
                "contact_name": "Test Contact",
                "contact_type": "patient",
                "call_type": "patient_feedback",
                "language": "en"
            }
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_initiate_test_call_invalid_phone(self, async_client: AsyncClient, auth_headers: dict, seeded_geography):
        """Test initiating test call with invalid phone number"""
        response = await async_client.post(
            "/api/v1/test-calls/initiate",
            headers=auth_headers,
            json={
                "geography_id": str(seeded_geography.id),
                "phone_number": "invalid",
                "contact_name": "Test Contact",
                "contact_type": "patient",
                "call_type": "patient_feedback",
                "language": "en"
            }
        )

        assert response.status_code == 400


@pytest.mark.contract
class TestTestCallActive:
    """Test GET /api/v1/test-calls/active"""

    @pytest.mark.asyncio
    async def test_list_active_test_calls(self, async_client: AsyncClient, auth_headers: dict):
        """Test listing active test calls"""
        response = await async_client.get(
            "/api/v1/test-calls/active",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_active_test_calls_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict):
        """Test that non-admin users cannot list active test calls"""
        response = await async_client.get(
            "/api/v1/test-calls/active",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestTestCallCancel:
    """Test DELETE /api/v1/test-calls/{call_id}"""

    @pytest.mark.asyncio
    async def test_cancel_test_call_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test canceling non-existent test call"""
        invalid_id = str(ObjectId())
        response = await async_client.delete(
            f"/api/v1/test-calls/{invalid_id}",
            headers=auth_headers
        )

        # Should return 404 for non-existent call
        assert response.status_code in [404, 400]

    @pytest.mark.asyncio
    async def test_cancel_test_call_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict):
        """Test that non-admin users cannot cancel test calls"""
        invalid_id = str(ObjectId())
        response = await async_client.delete(
            f"/api/v1/test-calls/{invalid_id}",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestQueueDebug:
    """Test GET /api/v1/test-calls/queues/{queue_id}/debug"""

    @pytest.mark.asyncio
    async def test_get_queue_debug_info(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test retrieving queue debug information"""
        response = await async_client.get(
            f"/api/v1/test-calls/queues/{seeded_call_queue.id}/debug",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Verify debug info structure
        assert "queue_id" in data
        assert "name" in data
        assert "state" in data
        assert "mode" in data
        assert "recipient_counts" in data
        assert "next_processing_window" in data

    @pytest.mark.asyncio
    async def test_get_queue_debug_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting debug info for non-existent queue"""
        invalid_id = str(ObjectId())
        response = await async_client.get(
            f"/api/v1/test-calls/queues/{invalid_id}/debug",
            headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_queue_debug_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot access debug info"""
        response = await async_client.get(
            f"/api/v1/test-calls/queues/{seeded_call_queue.id}/debug",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestForceProcessQueue:
    """Test POST /api/v1/test-calls/queues/{queue_id}/force-process"""

    @pytest.mark.asyncio
    async def test_force_process_queue_success(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test force processing a queue"""
        response = await async_client.post(
            f"/api/v1/test-calls/queues/{seeded_call_queue.id}/force-process",
            headers=auth_headers,
            json={}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "queue_id" in data
        assert "processed_count" in data
        assert isinstance(data["processed_count"], int)

    @pytest.mark.asyncio
    async def test_force_process_queue_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test force processing non-existent queue"""
        invalid_id = str(ObjectId())
        response = await async_client.post(
            f"/api/v1/test-calls/queues/{invalid_id}/force-process",
            headers=auth_headers,
            json={}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_force_process_queue_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot force process queues"""
        response = await async_client.post(
            f"/api/v1/test-calls/queues/{seeded_call_queue.id}/force-process",
            headers=user_auth_headers,
            json={}
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestSyncClarity:
    """Test POST /api/v1/test-calls/queues/{queue_id}/sync-clarity"""

    @pytest.mark.asyncio
    async def test_sync_clarity_success(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test manually triggering Clarity sync"""
        response = await async_client.post(
            f"/api/v1/test-calls/queues/{seeded_call_queue.id}/sync-clarity",
            headers=auth_headers,
            json={
                "action": "pull"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "queue_id" in data
        assert "action" in data
        assert "status" in data

    @pytest.mark.asyncio
    async def test_sync_clarity_with_push_action(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test Clarity sync with push action"""
        response = await async_client.post(
            f"/api/v1/test-calls/queues/{seeded_call_queue.id}/sync-clarity",
            headers=auth_headers,
            json={
                "action": "push"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["action"] in ["push", "both"]

    @pytest.mark.asyncio
    async def test_sync_clarity_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test syncing Clarity for non-existent queue"""
        invalid_id = str(ObjectId())
        response = await async_client.post(
            f"/api/v1/test-calls/queues/{invalid_id}/sync-clarity",
            headers=auth_headers,
            json={
                "action": "pull"
            }
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_sync_clarity_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot sync Clarity"""
        response = await async_client.post(
            f"/api/v1/test-calls/queues/{seeded_call_queue.id}/sync-clarity",
            headers=user_auth_headers,
            json={
                "action": "pull"
            }
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestTriggerRecipientCall:
    """Test POST /api/v1/test-calls/recipients/{recipient_id}/trigger-call"""

    @pytest.mark.asyncio
    async def test_trigger_recipient_call_success(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test manually triggering a call for a specific recipient"""
        response = await async_client.post(
            f"/api/v1/test-calls/recipients/{seeded_recipient.id}/trigger-call",
            headers=auth_headers,
            json={}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "recipient_id" in data
        assert "call_id" in data
        assert "status" in data

    @pytest.mark.asyncio
    async def test_trigger_recipient_call_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test triggering call for non-existent recipient"""
        invalid_id = str(ObjectId())
        response = await async_client.post(
            f"/api/v1/test-calls/recipients/{invalid_id}/trigger-call",
            headers=auth_headers,
            json={}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_recipient_call_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_recipient):
        """Test that non-admin users cannot trigger calls"""
        response = await async_client.post(
            f"/api/v1/test-calls/recipients/{seeded_recipient.id}/trigger-call",
            headers=user_auth_headers,
            json={}
        )

        assert response.status_code == 403
