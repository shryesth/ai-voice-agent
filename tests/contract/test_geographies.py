"""
Contract tests for Geography API endpoints.

These tests verify the API contract defined in specs/001-patient-feedback-api/contracts/geographies.md

Test Strategy (TDD):
1. Write tests FIRST (ensure they FAIL before implementation)
2. Tests define the contract that implementation must satisfy
3. All tests must pass before moving to next phase
"""

import pytest
from httpx import AsyncClient
from datetime import datetime


class TestGeographyCreate:
    """Test POST /api/v1/geographies"""

    @pytest.mark.asyncio
    async def test_create_geography_success(self, client: AsyncClient, admin_token: str):
        """Test successful geography creation with all fields"""
        response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "North America - East Coast",
                "description": "US East Coast operations covering NY, NJ, PA, MD",
                "region_code": "US-EAST",
                "retention_policy": {
                    "retention_days": 2555,
                    "archival_destination": "s3://backups/us-east/",
                    "auto_purge_enabled": False,
                    "compliance_notes": "HIPAA requires 7-year retention (2555 days)"
                },
                "metadata": {
                    "timezone": "America/New_York",
                    "primary_language": "en",
                    "contact_email": "ops-east@example.com"
                }
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert data["name"] == "North America - East Coast"
        assert data["description"] == "US East Coast operations covering NY, NJ, PA, MD"
        assert data["region_code"] == "US-EAST"

        # Verify retention policy
        assert data["retention_policy"]["retention_days"] == 2555
        assert data["retention_policy"]["archival_destination"] == "s3://backups/us-east/"
        assert data["retention_policy"]["auto_purge_enabled"] is False
        assert "HIPAA" in data["retention_policy"]["compliance_notes"]

        # Verify metadata
        assert data["metadata"]["timezone"] == "America/New_York"
        assert data["metadata"]["primary_language"] == "en"

        # Verify timestamps
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_geography_minimal(self, client: AsyncClient, admin_token: str):
        """Test geography creation with only required fields"""
        response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test Geography Minimal"
            }
        )

        assert response.status_code == 201
        data = response.json()

        assert data["name"] == "Test Geography Minimal"
        assert data.get("description") is None
        assert data.get("region_code") is None

        # Verify default retention policy
        assert "retention_policy" in data
        assert data["retention_policy"]["retention_days"] is None  # Indefinite
        assert data["retention_policy"]["auto_purge_enabled"] is False

    @pytest.mark.asyncio
    async def test_create_geography_requires_admin(self, client: AsyncClient, user_token: str):
        """Test that User role cannot create geography"""
        response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"name": "Should Fail"}
        )

        assert response.status_code == 403
        assert "Admin role required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_geography_duplicate_name(self, client: AsyncClient, admin_token: str):
        """Test that duplicate geography names are rejected"""
        # Create first geography
        await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Duplicate Test"}
        )

        # Attempt to create duplicate
        response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Duplicate Test"}
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_geography_unauthenticated(self, client: AsyncClient):
        """Test that unauthenticated requests are rejected"""
        response = await client.post(
            "/api/v1/geographies",
            json={"name": "Should Fail"}
        )

        assert response.status_code == 401


class TestGeographyList:
    """Test GET /api/v1/geographies"""

    @pytest.mark.asyncio
    async def test_list_geographies_empty(self, client: AsyncClient, admin_token: str):
        """Test listing geographies when none exist"""
        response = await client.get(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["skip"] == 0
        assert data["limit"] == 50
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_geographies_with_data(self, client: AsyncClient, admin_token: str):
        """Test listing geographies with multiple items"""
        # Create test geographies
        for i in range(3):
            await client.post(
                "/api/v1/geographies",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "name": f"Test Geography {i}",
                    "region_code": f"TEST-{i}"
                }
            )

        response = await client.get(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert all("id" in item for item in data["items"])
        assert all("name" in item for item in data["items"])

    @pytest.mark.asyncio
    async def test_list_geographies_filter_by_region(self, client: AsyncClient, admin_token: str):
        """Test filtering geographies by region_code"""
        # Create geographies with different regions
        await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "US East", "region_code": "US-EAST"}
        )
        await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "US West", "region_code": "US-WEST"}
        )

        response = await client.get(
            "/api/v1/geographies?region_code=US-EAST",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert data["items"][0]["region_code"] == "US-EAST"

    @pytest.mark.asyncio
    async def test_list_geographies_pagination(self, client: AsyncClient, admin_token: str):
        """Test pagination parameters"""
        # Create 10 geographies
        for i in range(10):
            await client.post(
                "/api/v1/geographies",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"name": f"Geography {i:02d}"}
            )

        response = await client.get(
            "/api/v1/geographies?skip=2&limit=3",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 10
        assert data["skip"] == 2
        assert data["limit"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_geographies_user_role(self, client: AsyncClient, user_token: str):
        """Test that User role can list geographies (read-only)"""
        response = await client.get(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 200


class TestGeographyGetById:
    """Test GET /api/v1/geographies/{geography_id}"""

    @pytest.mark.asyncio
    async def test_get_geography_by_id_success(self, client: AsyncClient, admin_token: str):
        """Test retrieving geography by ID"""
        # Create geography
        create_response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test Geography",
                "description": "Test Description",
                "region_code": "TEST"
            }
        )
        geography_id = create_response.json()["id"]

        # Retrieve by ID
        response = await client.get(
            f"/api/v1/geographies/{geography_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == geography_id
        assert data["name"] == "Test Geography"
        assert data["description"] == "Test Description"
        assert data["region_code"] == "TEST"

    @pytest.mark.asyncio
    async def test_get_geography_not_found(self, client: AsyncClient, admin_token: str):
        """Test retrieving non-existent geography"""
        response = await client.get(
            "/api/v1/geographies/507f1f77bcf86cd799439011",  # Valid ObjectId format
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestGeographyUpdate:
    """Test PATCH /api/v1/geographies/{geography_id}"""

    @pytest.mark.asyncio
    async def test_update_geography_success(self, client: AsyncClient, admin_token: str):
        """Test updating geography fields"""
        # Create geography
        create_response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Original Name"}
        )
        geography_id = create_response.json()["id"]

        # Update geography
        response = await client.patch(
            f"/api/v1/geographies/{geography_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "description": "Updated description",
                "retention_policy": {
                    "retention_days": 3650,
                    "compliance_notes": "Extended to 10 years"
                }
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == geography_id
        assert data["name"] == "Original Name"  # Unchanged
        assert data["description"] == "Updated description"
        assert data["retention_policy"]["retention_days"] == 3650

    @pytest.mark.asyncio
    async def test_update_geography_requires_admin(self, client: AsyncClient, user_token: str, admin_token: str):
        """Test that User role cannot update geography"""
        # Create geography as admin
        create_response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Test"}
        )
        geography_id = create_response.json()["id"]

        # Attempt update as user
        response = await client.patch(
            f"/api/v1/geographies/{geography_id}",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"description": "Should fail"}
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_geography_not_found(self, client: AsyncClient, admin_token: str):
        """Test updating non-existent geography"""
        response = await client.patch(
            "/api/v1/geographies/507f1f77bcf86cd799439011",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"description": "Should fail"}
        )

        assert response.status_code == 404


class TestGeographyDelete:
    """Test DELETE /api/v1/geographies/{geography_id}"""

    @pytest.mark.asyncio
    async def test_delete_geography_success(self, client: AsyncClient, admin_token: str):
        """Test soft deleting geography"""
        # Create geography
        create_response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "To Delete"}
        )
        geography_id = create_response.json()["id"]

        # Delete geography
        response = await client.delete(
            f"/api/v1/geographies/{geography_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 204

        # Verify geography is soft-deleted (not visible in normal list)
        list_response = await client.get(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        geographies = list_response.json()["items"]
        assert not any(g["id"] == geography_id for g in geographies)

    @pytest.mark.asyncio
    async def test_delete_geography_requires_admin(self, client: AsyncClient, user_token: str, admin_token: str):
        """Test that User role cannot delete geography"""
        # Create geography
        create_response = await client.post(
            "/api/v1/geographies",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Test"}
        )
        geography_id = create_response.json()["id"]

        # Attempt delete as user
        response = await client.delete(
            f"/api/v1/geographies/{geography_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_geography_not_found(self, client: AsyncClient, admin_token: str):
        """Test deleting non-existent geography"""
        response = await client.delete(
            "/api/v1/geographies/507f1f77bcf86cd799439011",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 404
