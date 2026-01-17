"""
Contract tests for Campaign API endpoints.

These tests verify the API contract defined in specs/001-patient-feedback-api/contracts/campaigns.md

Test Strategy (TDD):
1. Write tests FIRST (ensure they FAIL before implementation)
2. Tests define the contract that implementation must satisfy
3. All tests must pass before moving to next phase
"""

import pytest
from httpx import AsyncClient
from datetime import datetime


@pytest.fixture
async def geography_id(client: AsyncClient, admin_token: str) -> str:
    """Create a test geography and return its ID"""
    response = await client.post(
        "/api/v1/geographies",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Test Geography for Campaigns"}
    )
    return response.json()["id"]


class TestCampaignCreate:
    """Test POST /api/v1/geographies/{geography_id}/campaigns"""

    @pytest.mark.asyncio
    async def test_create_campaign_success(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test successful campaign creation with all fields"""
        response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Post-Vaccination Feedback - January 2026",
                "config": {
                    "max_concurrent_calls": 10,
                    "time_windows": [
                        {
                            "start_time": "09:00:00",
                            "end_time": "17:00:00",
                            "days_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"]
                        }
                    ],
                    "patient_list": ["+12025551234", "+12025555678", "+13105559999"],
                    "language_preference": "en"
                }
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert data["geography_id"] == geography_id
        assert data["name"] == "Post-Vaccination Feedback - January 2026"
        assert data["state"] == "draft"

        # Verify config
        assert data["config"]["max_concurrent_calls"] == 10
        assert len(data["config"]["time_windows"]) == 1
        assert data["config"]["time_windows"][0]["start_time"] == "09:00:00"
        assert len(data["config"]["patient_list"]) == 3

        # Verify stats initialized
        assert data["stats"]["total_calls"] == 3
        assert data["stats"]["queued_count"] == 0
        assert data["stats"]["completed_count"] == 0

        # Verify timestamps
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_campaign_minimal(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test campaign creation with minimal config"""
        response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Minimal Campaign",
                "config": {
                    "patient_list": ["+12025551234"]
                }
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Verify defaults
        assert data["config"]["max_concurrent_calls"] == 10  # Default
        assert data["config"]["language_preference"] == "en"  # Default
        assert data["config"]["time_windows"] == []  # Empty = always

    @pytest.mark.asyncio
    async def test_create_campaign_requires_admin(self, client: AsyncClient, user_token: str, geography_id: str):
        """Test that User role cannot create campaign"""
        response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "name": "Should Fail",
                "config": {"patient_list": ["+12025551234"]}
            }
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_campaign_invalid_phone_format(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test that invalid phone numbers are rejected"""
        response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Invalid Phone",
                "config": {
                    "patient_list": ["202-555-1234"]  # Not E.164 format
                }
            }
        )

        assert response.status_code == 422
        assert "E.164" in str(response.json())

    @pytest.mark.asyncio
    async def test_create_campaign_geography_not_found(self, client: AsyncClient, admin_token: str):
        """Test creating campaign with non-existent geography"""
        response = await client.post(
            "/api/v1/geographies/507f1f77bcf86cd799439011/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Should Fail",
                "config": {"patient_list": ["+12025551234"]}
            }
        )

        assert response.status_code == 404


class TestCampaignList:
    """Test GET /api/v1/campaigns"""

    @pytest.mark.asyncio
    async def test_list_campaigns_empty(self, client: AsyncClient, admin_token: str):
        """Test listing campaigns when none exist"""
        response = await client.get(
            "/api/v1/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_campaigns_with_data(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test listing campaigns"""
        # Create test campaigns
        for i in range(3):
            await client.post(
                f"/api/v1/geographies/{geography_id}/campaigns",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "name": f"Test Campaign {i}",
                    "config": {"patient_list": [f"+1202555{i:04d}"]}
                }
            )

        response = await client.get(
            "/api/v1/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_campaigns_filter_by_geography(self, client: AsyncClient, admin_token: str):
        """Test filtering campaigns by geography_id"""
        # Create two geographies
        geo1 = (await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Geo 1"}
        )).json()["id"]

        geo2 = (await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Geo 2"}
        )).json()["id"]

        # Create campaigns in different geographies
        await client.post(
            f"/api/v1/geographies/{geo1}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Campaign Geo1", "config": {"patient_list": ["+12025551234"]}}
        )
        await client.post(
            f"/api/v1/geographies/{geo2}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Campaign Geo2", "config": {"patient_list": ["+12025555678"]}}
        )

        # Filter by geo1
        response = await client.get(
            f"/api/v1/campaigns?geography_id={geo1}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["geography_id"] == geo1

    @pytest.mark.asyncio
    async def test_list_campaigns_filter_by_state(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test filtering campaigns by state"""
        # Create draft campaign
        response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Draft Campaign", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = response.json()["id"]

        # Start campaign to change state
        await client.post(
            f"/api/v1/campaigns/{campaign_id}/start",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Filter by active state
        response = await client.get(
            "/api/v1/campaigns?state=active",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(item["state"] == "active" for item in data["items"])


class TestCampaignGetById:
    """Test GET /api/v1/campaigns/{campaign_id}"""

    @pytest.mark.asyncio
    async def test_get_campaign_by_id_success(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test retrieving campaign by ID"""
        # Create campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test Campaign",
                "config": {"patient_list": ["+12025551234", "+12025555678"]}
            }
        )
        campaign_id = create_response.json()["id"]

        # Retrieve by ID
        response = await client.get(
            f"/api/v1/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == campaign_id
        assert data["name"] == "Test Campaign"
        assert len(data["config"]["patient_list"]) == 2

    @pytest.mark.asyncio
    async def test_get_campaign_not_found(self, client: AsyncClient, admin_token: str):
        """Test retrieving non-existent campaign"""
        response = await client.get(
            "/api/v1/campaigns/507f1f77bcf86cd799439011",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404


class TestCampaignUpdate:
    """Test PATCH /api/v1/campaigns/{campaign_id}"""

    @pytest.mark.asyncio
    async def test_update_campaign_draft_success(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test updating campaign in draft state"""
        # Create campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Original Name",
                "config": {"patient_list": ["+12025551234"]}
            }
        )
        campaign_id = create_response.json()["id"]

        # Update campaign
        response = await client.patch(
            f"/api/v1/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Updated Name",
                "config": {"max_concurrent_calls": 15}
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["config"]["max_concurrent_calls"] == 15

    @pytest.mark.asyncio
    async def test_update_campaign_active_fails(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test that active campaigns cannot be updated"""
        # Create and start campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Test", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = create_response.json()["id"]

        await client.post(
            f"/api/v1/campaigns/{campaign_id}/start",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Attempt update
        response = await client.patch(
            f"/api/v1/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Should Fail"}
        )

        assert response.status_code == 409
        assert "Pause campaign first" in response.json()["detail"]


class TestCampaignStateTransitions:
    """Test campaign state transition endpoints"""

    @pytest.mark.asyncio
    async def test_start_campaign(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test POST /api/v1/campaigns/{campaign_id}/start"""
        # Create campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "To Start",
                "config": {"patient_list": ["+12025551234", "+12025555678"]}
            }
        )
        campaign_id = create_response.json()["id"]

        # Start campaign
        response = await client.post(
            f"/api/v1/campaigns/{campaign_id}/start",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["state"] == "active"
        assert "started_at" in data
        assert "Queue entries created" in data["message"]

    @pytest.mark.asyncio
    async def test_pause_campaign(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test POST /api/v1/campaigns/{campaign_id}/pause"""
        # Create and start campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "To Pause", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = create_response.json()["id"]

        await client.post(
            f"/api/v1/campaigns/{campaign_id}/start",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Pause campaign
        response = await client.post(
            f"/api/v1/campaigns/{campaign_id}/pause",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "paused"

    @pytest.mark.asyncio
    async def test_resume_campaign(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test POST /api/v1/campaigns/{campaign_id}/resume"""
        # Create, start, and pause campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "To Resume", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = create_response.json()["id"]

        await client.post(f"/api/v1/campaigns/{campaign_id}/start", headers={"Authorization": f"Bearer {admin_token}"})
        await client.post(f"/api/v1/campaigns/{campaign_id}/pause", headers={"Authorization": f"Bearer {admin_token}"})

        # Resume campaign
        response = await client.post(
            f"/api/v1/campaigns/{campaign_id}/resume",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "active"

    @pytest.mark.asyncio
    async def test_cancel_campaign(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test POST /api/v1/campaigns/{campaign_id}/cancel"""
        # Create and start campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "To Cancel", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = create_response.json()["id"]

        await client.post(f"/api/v1/campaigns/{campaign_id}/start", headers={"Authorization": f"Bearer {admin_token}"})

        # Cancel campaign
        response = await client.post(
            f"/api/v1/campaigns/{campaign_id}/cancel",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "cancelled"
        assert "completed_at" in data

    @pytest.mark.asyncio
    async def test_start_already_active_fails(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test that starting an already active campaign fails"""
        # Create and start campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Test", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = create_response.json()["id"]

        await client.post(f"/api/v1/campaigns/{campaign_id}/start", headers={"Authorization": f"Bearer {admin_token}"})

        # Attempt to start again
        response = await client.post(
            f"/api/v1/campaigns/{campaign_id}/start",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 409
        assert "already active" in response.json()["detail"]


class TestCampaignStatus:
    """Test GET /api/v1/campaigns/{campaign_id}/status"""

    @pytest.mark.asyncio
    async def test_campaign_status(self, client: AsyncClient, admin_token: str, geography_id: str):
        """Test retrieving campaign execution status"""
        # Create and start campaign
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Status Test", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = create_response.json()["id"]

        await client.post(f"/api/v1/campaigns/{campaign_id}/start", headers={"Authorization": f"Bearer {admin_token}"})

        # Get status
        response = await client.get(
            f"/api/v1/campaigns/{campaign_id}/status",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["campaign_id"] == campaign_id
        assert data["state"] == "active"
        assert "stats" in data
        assert "progress_percent" in data
        assert "current_concurrency" in data

    @pytest.mark.asyncio
    async def test_campaign_status_user_role(self, client: AsyncClient, user_token: str, admin_token: str, geography_id: str):
        """Test that User role can view campaign status"""
        # Create campaign as admin
        create_response = await client.post(
            f"/api/v1/geographies/{geography_id}/campaigns",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Test", "config": {"patient_list": ["+12025551234"]}}
        )
        campaign_id = create_response.json()["id"]

        # Get status as user
        response = await client.get(
            f"/api/v1/campaigns/{campaign_id}/status",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 200
