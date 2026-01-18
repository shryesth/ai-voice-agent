"""
Contract tests for authentication endpoints.

Tests the API contract for:
- POST /api/v1/auth/login
- GET /api/v1/auth/me

Following TDD: These tests will FAIL until implementation is complete.
"""

import pytest
from httpx import AsyncClient
from fastapi import status

from backend.app.main import app


@pytest.mark.asyncio
class TestAuthLogin:
    """Test POST /api/v1/auth/login endpoint contract."""

    async def test_login_success(self, async_client: AsyncClient, test_admin_user, seeded_admin_user):
        """
        Test successful login with valid credentials.

        Expected:
        - Status: 200 OK
        - Response includes: access_token, token_type, expires_in, user
        - User object includes: email, role, is_active
        """
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_admin_user["email"],
                "password": test_admin_user["password"],
            }
        )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "access_token" in data
        assert data["access_token"] is not None
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["expires_in"] > 0

        # Validate user object
        assert "user" in data
        user = data["user"]
        assert user["email"] == test_admin_user["email"]
        assert user["role"] == "admin"
        assert user["is_active"] is True

    async def test_login_invalid_email(self, async_client: AsyncClient):
        """
        Test login with invalid email format.

        Expected:
        - Status: 422 Unprocessable Entity
        - Response includes validation error details
        """
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "not-an-email",
                "password": "validpassword123",
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        data = response.json()
        assert "detail" in data
        # Check that email field is mentioned in error
        errors = data["detail"]
        assert any("email" in str(error.get("loc", [])) for error in errors)

    async def test_login_short_password(self, async_client: AsyncClient):
        """
        Test login with password shorter than minimum length (8 chars).

        Expected:
        - Status: 422 Unprocessable Entity
        - Response includes validation error for password field
        """
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "short",  # Less than 8 characters
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        data = response.json()
        assert "detail" in data
        errors = data["detail"]
        assert any("password" in str(error.get("loc", [])) for error in errors)

    async def test_login_incorrect_credentials(self, async_client: AsyncClient):
        """
        Test login with incorrect email or password.

        Expected:
        - Status: 401 Unauthorized
        - Response detail: "Incorrect email or password"
        """
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "wrongpassword123",
            }
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Incorrect email or password"

    async def test_login_missing_fields(self, async_client: AsyncClient):
        """
        Test login with missing required fields.

        Expected:
        - Status: 422 Unprocessable Entity
        """
        # Missing password
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Missing email
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"password": "password123"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Empty body
        response = await async_client.post(
            "/api/v1/auth/login",
            json={}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
class TestAuthMe:
    """Test GET /api/v1/auth/me endpoint contract."""

    async def test_get_current_user_success(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test getting current user info with valid token.

        Expected:
        - Status: 200 OK
        - Response includes: email, role, is_active, created_at, last_login
        """
        response = await async_client.get(
            "/api/v1/auth/me",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "email" in data
        assert "role" in data
        assert "is_active" in data
        assert "created_at" in data
        # last_login is optional
        assert "last_login" in data or data.get("last_login") is None

    async def test_get_current_user_missing_token(self, async_client: AsyncClient):
        """
        Test accessing /me endpoint without authentication token.

        Expected:
        - Status: 401 Unauthorized
        - Response detail: "Not authenticated"
        """
        response = await async_client.get("/api/v1/auth/me")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        data = response.json()
        assert "detail" in data
        assert "authenticated" in data["detail"].lower()

    async def test_get_current_user_invalid_token(self, async_client: AsyncClient):
        """
        Test accessing /me endpoint with invalid token.

        Expected:
        - Status: 401 Unauthorized
        - Response detail: "Could not validate credentials"
        """
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token_123"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        data = response.json()
        assert "detail" in data

    async def test_get_current_user_malformed_header(self, async_client: AsyncClient):
        """
        Test accessing /me endpoint with malformed Authorization header.

        Expected:
        - Status: 401 Unauthorized
        """
        # Missing "Bearer" prefix
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "InvalidFormat"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # Empty token
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer "}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
class TestAuthWorkflow:
    """Test complete authentication workflow."""

    async def test_login_then_access_protected_endpoint(
        self,
        async_client: AsyncClient,
        test_admin_user,
        seeded_admin_user
    ):
        """
        Test complete flow: login -> receive token -> access protected endpoint.

        Expected:
        - Login succeeds and returns token
        - Token can be used to access /me endpoint
        - User info matches logged-in user
        """
        # Step 1: Login
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_admin_user["email"],
                "password": test_admin_user["password"],
            }
        )
        assert login_response.status_code == status.HTTP_200_OK
        login_data = login_response.json()
        access_token = login_data["access_token"]

        # Step 2: Use token to access protected endpoint
        me_response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert me_response.status_code == status.HTTP_200_OK
        me_data = me_response.json()

        # Step 3: Verify user info matches
        assert me_data["email"] == test_admin_user["email"]
        assert me_data["role"] == "admin"
        assert me_data["is_active"] is True
