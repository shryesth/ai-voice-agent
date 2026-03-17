"""
Contract tests for Recipient API endpoints.

Tests verify the API contract for recipient management, call tracking,
and DLQ operations.
"""

import pytest
from httpx import AsyncClient
from bson import ObjectId


@pytest.mark.contract
class TestRecipientCreate:
    """Test POST /api/v1/queues/{queue_id}/recipients"""

    @pytest.mark.asyncio
    async def test_create_recipient_success(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test successful recipient creation"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/recipients",
            headers=auth_headers,
            json={
                "contact_phone": "+12025551234",
                "contact_name": "John Doe",
                "contact_type": "patient",
                "language": "en",
                "priority": 0,
                "event_info": {
                    "nexus_verification_id": "test-123",
                    "event_type": "Suivi des Enfants",
                    "event_category": "child_vaccination",
                    "confirmation_message_key": "child_vaccination_rr1",
                    "event_date": "2026-01-15T10:00:00Z",
                    "facility_name": "Test Clinic",
                    "requires_side_effects": True
                }
            }
        )

        assert response.status_code == 201
        data = response.json()

        assert data["contact_phone"] == "+12025551234"
        assert data["contact_name"] == "John Doe"
        assert data["contact_type"] == "patient"
        assert data["language"] == "en"
        assert data["status"] == "pending"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_recipient_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_call_queue):
        """Test that non-admin users cannot create recipients"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/recipients",
            headers=user_auth_headers,
            json={
                "contact_phone": "+12025551234",
                "contact_name": "John Doe",
                "contact_type": "patient",
                "language": "en"
            }
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_recipient_invalid_phone(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test recipient creation with invalid phone number"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/recipients",
            headers=auth_headers,
            json={
                "contact_phone": "invalid",
                "contact_name": "John Doe",
                "contact_type": "patient",
                "language": "en"
            }
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_recipient_duplicate_phone(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test creating duplicate recipient with same phone in queue"""
        # Create first recipient
        await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/recipients",
            headers=auth_headers,
            json={
                "contact_phone": "+12025551234",
                "contact_name": "John Doe",
                "contact_type": "patient",
                "language": "en"
            }
        )

        # Try to create duplicate
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/recipients",
            headers=auth_headers,
            json={
                "contact_phone": "+12025551234",
                "contact_name": "Jane Doe",
                "contact_type": "patient",
                "language": "en"
            }
        )

        # Should fail due to duplicate
        assert response.status_code == 400


@pytest.mark.contract
class TestRecipientBulkCreate:
    """Test POST /api/v1/queues/{queue_id}/recipients/bulk"""

    @pytest.mark.asyncio
    async def test_bulk_create_recipients_success(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test bulk creating multiple recipients"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/recipients/bulk",
            headers=auth_headers,
            json={
                "recipients": [
                    {
                        "contact_phone": "+12025551234",
                        "contact_name": "John Doe",
                        "contact_type": "patient",
                        "language": "en"
                    },
                    {
                        "contact_phone": "+12025555678",
                        "contact_name": "Jane Doe",
                        "contact_type": "guardian",
                        "language": "en"
                    }
                ]
            }
        )

        assert response.status_code == 201
        data = response.json()

        assert "items" in data
        assert len(data["items"]) == 2
        assert data["items"][0]["contact_phone"] == "+12025551234"
        assert data["items"][1]["contact_phone"] == "+12025555678"

    @pytest.mark.asyncio
    async def test_bulk_create_with_errors(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test bulk create with mixed valid and invalid recipients"""
        response = await async_client.post(
            f"/api/v1/queues/{seeded_call_queue.id}/recipients/bulk",
            headers=auth_headers,
            json={
                "recipients": [
                    {
                        "contact_phone": "+12025551234",
                        "contact_name": "John Doe",
                        "contact_type": "patient",
                        "language": "en"
                    },
                    {
                        "contact_phone": "invalid",
                        "contact_name": "Invalid User",
                        "contact_type": "patient",
                        "language": "en"
                    }
                ]
            }
        )

        assert response.status_code == 201
        data = response.json()

        # At least the valid one should be created
        assert len(data["items"]) >= 1


@pytest.mark.contract
class TestRecipientList:
    """Test GET /api/v1/queues/{queue_id}/recipients"""

    @pytest.mark.asyncio
    async def test_list_recipients_success(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test listing recipients in a queue"""
        queue_id = seeded_recipient.queue_id
        response = await async_client.get(
            f"/api/v1/queues/{queue_id}/recipients",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_list_recipients_with_status_filter(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test listing recipients filtered by status"""
        queue_id = seeded_recipient.queue_id
        response = await async_client.get(
            f"/api/v1/queues/{queue_id}/recipients?status=pending",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # All returned recipients should have pending status
        for recipient in data["items"]:
            assert recipient["status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_recipients_pagination(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test recipient listing with pagination"""
        queue_id = seeded_recipient.queue_id
        response = await async_client.get(
            f"/api/v1/queues/{queue_id}/recipients?skip=0&limit=10",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["skip"] == 0
        assert data["limit"] == 10
        assert len(data["items"]) <= 10


@pytest.mark.contract
class TestRecipientGet:
    """Test GET /api/v1/recipients/{recipient_id}"""

    @pytest.mark.asyncio
    async def test_get_recipient_success(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test retrieving a recipient by ID"""
        response = await async_client.get(
            f"/api/v1/recipients/{seeded_recipient.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(seeded_recipient.id)
        assert data["contact_name"] == seeded_recipient.contact_name
        assert data["status"] == seeded_recipient.status.value

    @pytest.mark.asyncio
    async def test_get_recipient_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test retrieving non-existent recipient"""
        invalid_id = str(ObjectId())
        response = await async_client.get(
            f"/api/v1/recipients/{invalid_id}",
            headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_recipient_user_phone_redaction(self, async_client: AsyncClient, user_auth_headers: dict, seeded_recipient):
        """Test that non-admin users have phone numbers redacted"""
        response = await async_client.get(
            f"/api/v1/recipients/{seeded_recipient.id}",
            headers=user_auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Phone should be redacted (masked)
        phone = data.get("contact_phone", "")
        if phone:
            # Check for redaction pattern (e.g., +12****34)
            assert "****" in phone or phone != seeded_recipient.contact_phone


@pytest.mark.contract
class TestRecipientUpdate:
    """Test PATCH /api/v1/recipients/{recipient_id}"""

    @pytest.mark.asyncio
    async def test_update_recipient_success(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test updating recipient details"""
        response = await async_client.patch(
            f"/api/v1/recipients/{seeded_recipient.id}",
            headers=auth_headers,
            json={
                "contact_name": "Updated Name"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["contact_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_recipient_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_recipient):
        """Test that non-admin users cannot update recipients"""
        response = await async_client.patch(
            f"/api/v1/recipients/{seeded_recipient.id}",
            headers=user_auth_headers,
            json={
                "contact_name": "Unauthorized Update"
            }
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestRecipientDelete:
    """Test DELETE /api/v1/recipients/{recipient_id}"""

    @pytest.mark.asyncio
    async def test_delete_recipient_success(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test deleting a pending recipient"""
        response = await async_client.delete(
            f"/api/v1/recipients/{seeded_recipient.id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify recipient is deleted
        get_response = await async_client.get(
            f"/api/v1/recipients/{seeded_recipient.id}",
            headers=auth_headers
        )

        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_recipient_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_recipient):
        """Test that non-admin users cannot delete recipients"""
        response = await async_client.delete(
            f"/api/v1/recipients/{seeded_recipient.id}",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestRecipientTimeline:
    """Test GET /api/v1/recipients/{recipient_id}/timeline"""

    @pytest.mark.asyncio
    async def test_get_recipient_timeline(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test retrieving recipient call timeline"""
        response = await async_client.get(
            f"/api/v1/recipients/{seeded_recipient.id}/timeline",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "recipient_id" in data
        assert "contact_name" in data
        assert "status" in data
        assert "timeline" in data
        assert isinstance(data["timeline"], list)

    @pytest.mark.asyncio
    async def test_get_recipient_timeline_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting timeline for non-existent recipient"""
        invalid_id = str(ObjectId())
        response = await async_client.get(
            f"/api/v1/recipients/{invalid_id}/timeline",
            headers=auth_headers
        )

        assert response.status_code == 404


@pytest.mark.contract
class TestRecipientSkip:
    """Test POST /api/v1/recipients/{recipient_id}/skip"""

    @pytest.mark.asyncio
    async def test_skip_recipient_success(self, async_client: AsyncClient, auth_headers: dict, seeded_recipient):
        """Test skipping a recipient"""
        response = await async_client.post(
            f"/api/v1/recipients/{seeded_recipient.id}/skip",
            headers=auth_headers,
            json={
                "reason": "Contact requested to be skipped"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_skip_recipient_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_recipient):
        """Test that non-admin users cannot skip recipients"""
        response = await async_client.post(
            f"/api/v1/recipients/{seeded_recipient.id}/skip",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestRecipientDLQ:
    """Test DLQ endpoints"""

    @pytest.mark.asyncio
    async def test_list_dlq_recipients(self, async_client: AsyncClient, auth_headers: dict):
        """Test listing recipients in DLQ"""
        response = await async_client.get(
            "/api/v1/recipients/dlq",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_dlq_by_queue(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test listing DLQ recipients filtered by queue"""
        response = await async_client.get(
            f"/api/v1/recipients/dlq?queue_id={seeded_call_queue.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "items" in data

    @pytest.mark.asyncio
    async def test_list_dlq_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict):
        """Test that non-admin users cannot access DLQ"""
        response = await async_client.get(
            "/api/v1/recipients/dlq",
            headers=user_auth_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_retry_dlq_recipient_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_recipient):
        """Test that non-admin users cannot retry DLQ recipients"""
        response = await async_client.post(
            f"/api/v1/recipients/dlq/{seeded_recipient.id}/retry",
            headers=user_auth_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_dlq_recipient_non_admin_forbidden(self, async_client: AsyncClient, user_auth_headers: dict, seeded_recipient):
        """Test that non-admin users cannot delete DLQ recipients"""
        response = await async_client.delete(
            f"/api/v1/recipients/dlq/{seeded_recipient.id}",
            headers=user_auth_headers
        )

        assert response.status_code == 403


@pytest.mark.contract
class TestRecipientSummary:
    """Test GET /api/v1/queues/{queue_id}/summary"""

    @pytest.mark.asyncio
    async def test_get_recipient_summary(self, async_client: AsyncClient, auth_headers: dict, seeded_call_queue):
        """Test retrieving recipient summary statistics"""
        response = await async_client.get(
            f"/api/v1/queues/{seeded_call_queue.id}/summary",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "total_recipients" in data
        assert "by_status" in data
        assert "urgent_count" in data

        # Verify status counts
        by_status = data["by_status"]
        assert isinstance(by_status, dict)
